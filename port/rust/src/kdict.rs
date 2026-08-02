#[cfg(not(target_arch = "wasm32"))]
use memmap2::Mmap;
#[cfg(not(target_arch = "wasm32"))]
use std::fs::File;
#[cfg(not(target_arch = "wasm32"))]
use std::path::Path;

#[repr(C, packed)]
#[derive(Debug, Copy, Clone)]
pub struct KDictHeader {
    pub magic: [u8; 4],
    pub version: u32,
    pub num_entries: u32,
    pub table_size: u32,
    pub default_cost: f32,
    pub unknown_cost: f32,
    pub max_word_length: u32,
    pub padding: u32,
}

#[repr(C, packed)]
#[derive(Debug, Copy, Clone)]
pub struct KDictEntry {
    pub name_offset: u32,
    pub cost: f32,
}

#[derive(Debug)]
pub enum DataSource {
    #[cfg(not(target_arch = "wasm32"))]
    Mmap(Mmap),
    Owned(Vec<u8>),
}

impl DataSource {
    fn as_ptr(&self) -> *const u8 {
        match self {
            #[cfg(not(target_arch = "wasm32"))]
            DataSource::Mmap(m) => m.as_ptr(),
            DataSource::Owned(v) => v.as_ptr(),
        }
    }

    fn len(&self) -> usize {
        match self {
            #[cfg(not(target_arch = "wasm32"))]
            DataSource::Mmap(m) => m.len(),
            DataSource::Owned(v) => v.len(),
        }
    }

    fn as_slice(&self) -> &[u8] {
        match self {
            #[cfg(not(target_arch = "wasm32"))]
            DataSource::Mmap(m) => m,
            DataSource::Owned(v) => v,
        }
    }
}

pub const WORD_SEGMENT: u32 = 1 << 0;
pub const WORD_SPELLCHECK: u32 = 1 << 1;
pub const WORD_AUTOCOMPLETE: u32 = 1 << 2;
pub const WORD_TYPO_SURFACE: u32 = 1 << 3;
pub const WORD_SUPPLEMENTAL: u32 = 1 << 4;

#[derive(Debug, Clone, PartialEq)]
pub struct KDictWord {
    pub word: String,
    pub flags: u32,
    pub cost: f32,
}

pub struct KDict {
    // Keep source alive. Pointers below point into this source.
    #[allow(dead_code)]
    pub source: DataSource,
    pub header: *const KDictHeader,
    pub table: *const KDictEntry,
    pub string_pool: *const u8,
    pub table_mask: u32,
}

impl KDict {
    #[cfg(not(target_arch = "wasm32"))]
    pub fn load(path: impl AsRef<Path>) -> std::io::Result<Self> {
        let file = File::open(path)?;
        let mmap = unsafe { Mmap::map(&file)? };
        Self::from_source(DataSource::Mmap(mmap))
    }

    pub fn from_bytes(bytes: Vec<u8>) -> std::io::Result<Self> {
        Self::from_source(DataSource::Owned(bytes))
    }

    fn from_source(source: DataSource) -> std::io::Result<Self> {
        if source.len() < std::mem::size_of::<KDictHeader>() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "File too small",
            ));
        }

        let base_ptr = source.as_ptr();
        let header_ptr = base_ptr as *const KDictHeader;
        let header = unsafe { &*header_ptr };

        if &header.magic != b"KDIC" {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Invalid magic",
            ));
        }
        if !matches!(header.version, 1 | 2) {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Unsupported KDIC version",
            ));
        }

        let table_offset = std::mem::size_of::<KDictHeader>();
        // Check bounds would be good here
        let table_ptr = unsafe { base_ptr.add(table_offset) } as *const KDictEntry;

        let table_bytes = header.table_size as usize * std::mem::size_of::<KDictEntry>();
        let pool_offset = table_offset + table_bytes;

        if pool_offset > source.len() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "File truncated",
            ));
        }
        if header.version >= 2 {
            let extension_offset = header.padding as usize;
            if extension_offset < pool_offset || extension_offset + 16 > source.len() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "Invalid KDIC v2 extension offset",
                ));
            }
            if &source.as_slice()[extension_offset..extension_offset + 4] != b"KDX2" {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "Invalid KDIC v2 extension",
                ));
            }
        }

        let pool_ptr = unsafe { base_ptr.add(pool_offset) };

        Ok(KDict {
            source,
            header: header_ptr,
            table: table_ptr,
            string_pool: pool_ptr,
            table_mask: header.table_size - 1,
        })
    }

    pub fn get_pool_bytes(&self, offset: u32) -> &[u8] {
        unsafe {
            let ptr = self.string_pool.add(offset as usize);
            let mut len = 0;
            while *ptr.add(len) != 0 {
                len += 1;
            }
            std::slice::from_raw_parts(ptr, len)
        }
    }

    pub fn get_pool_ptr(&self, offset: u32) -> *const u8 {
        unsafe { self.string_pool.add(offset as usize) }
    }

    pub fn cost(&self, word: &str) -> Option<f32> {
        let hash = crate::utils::djb2_hash(word.as_bytes());
        let mut index = hash & self.table_mask;
        loop {
            let entry = unsafe { &*self.table.add(index as usize) };
            if entry.name_offset == 0 {
                return None;
            }
            if self.get_pool_bytes(entry.name_offset) == word.as_bytes() {
                return Some(entry.cost);
            }
            index = (index + 1) & self.table_mask;
        }
    }

    pub fn default_cost(&self) -> f32 {
        unsafe { (*self.header).default_cost }
    }

    pub fn version(&self) -> u32 {
        unsafe { (*self.header).version }
    }

    pub fn has_unified_metadata(&self) -> bool {
        self.version() >= 2
    }

    fn read_u32(&self, offset: usize) -> Option<u32> {
        let bytes = self.source.as_slice().get(offset..offset + 4)?;
        Some(u32::from_le_bytes(bytes.try_into().ok()?))
    }

    fn read_f32(&self, offset: usize) -> Option<f32> {
        self.read_u32(offset).map(f32::from_bits)
    }

    /// Return all typed lexical records embedded in KDIC v2.
    pub fn lexical_entries(&self) -> Vec<KDictWord> {
        if !self.has_unified_metadata() {
            return self
                .words_with_costs()
                .into_iter()
                .map(|(word, cost)| KDictWord {
                    word,
                    flags: WORD_SEGMENT | WORD_SPELLCHECK | WORD_AUTOCOMPLETE,
                    cost,
                })
                .collect();
        }
        let extension = unsafe { (*self.header).padding as usize };
        let count = self.read_u32(extension + 8).unwrap_or(0) as usize;
        let mut entries = Vec::with_capacity(count);
        let mut cursor = extension + 16;
        for _ in 0..count {
            let Some(name_offset) = self.read_u32(cursor) else {
                break;
            };
            let Some(flags) = self.read_u32(cursor + 4) else {
                break;
            };
            let Some(cost) = self.read_f32(cursor + 8) else {
                break;
            };
            cursor += 12;
            if let Ok(word) = std::str::from_utf8(self.get_pool_bytes(name_offset)) {
                entries.push(KDictWord {
                    word: word.to_owned(),
                    flags,
                    cost,
                });
            }
        }
        entries
    }

    /// Return approved exact typo mappings embedded in KDIC v2.
    pub fn typo_corrections(&self) -> Vec<(String, String)> {
        if !self.has_unified_metadata() {
            return Vec::new();
        }
        let extension = unsafe { (*self.header).padding as usize };
        let word_count = self.read_u32(extension + 8).unwrap_or(0) as usize;
        let typo_count = self.read_u32(extension + 12).unwrap_or(0) as usize;
        let mut cursor = extension + 16 + word_count * 12;
        let mut corrections = Vec::with_capacity(typo_count);
        for _ in 0..typo_count {
            let Some(typed_offset) = self.read_u32(cursor) else {
                break;
            };
            let Some(correction_offset) = self.read_u32(cursor + 4) else {
                break;
            };
            cursor += 8;
            let Ok(typed) = std::str::from_utf8(self.get_pool_bytes(typed_offset)) else {
                continue;
            };
            let Ok(correction) = std::str::from_utf8(self.get_pool_bytes(correction_offset)) else {
                continue;
            };
            corrections.push((typed.to_owned(), correction.to_owned()));
        }
        corrections
    }

    /// Copy all dictionary entries into safe Rust values.
    ///
    /// This is primarily used to build secondary indexes such as spellcheck
    /// candidate maps. Segmentation continues to query the compact KDIC hash
    /// table directly.
    pub fn words_with_costs(&self) -> Vec<(String, f32)> {
        let table_size = unsafe { (*self.header).table_size as usize };
        let mut words = Vec::with_capacity(unsafe { (*self.header).num_entries as usize });
        for index in 0..table_size {
            let entry = unsafe { &*self.table.add(index) };
            if entry.name_offset == 0 {
                continue;
            }
            if let Ok(word) = std::str::from_utf8(self.get_pool_bytes(entry.name_offset)) {
                words.push((word.to_owned(), entry.cost));
            }
        }
        words
    }
}

unsafe impl Send for KDict {}
unsafe impl Sync for KDict {}

#[repr(C, packed)]
#[derive(Debug, Copy, Clone)]
pub struct KHypHeader {
    pub magic: [u8; 4],
    pub version: u32,
    pub num_entries: u32,
    pub table_size: u32,
    pub padding: [u32; 4],
}

#[repr(C, packed)]
#[derive(Debug, Copy, Clone)]
pub struct KHypEntry {
    pub key_offset: u32,
    pub val_offset: u32,
}

pub struct KHypDict {
    #[allow(dead_code)]
    pub source: DataSource,
    pub header: *const KHypHeader,
    pub table: *const KHypEntry,
    pub string_pool: *const u8,
    pub table_mask: u32,
}

impl KHypDict {
    #[cfg(not(target_arch = "wasm32"))]
    pub fn load(path: impl AsRef<Path>) -> std::io::Result<Self> {
        let file = File::open(path)?;
        let mmap = unsafe { Mmap::map(&file)? };
        Self::from_source(DataSource::Mmap(mmap))
    }

    pub fn from_bytes(bytes: Vec<u8>) -> std::io::Result<Self> {
        Self::from_source(DataSource::Owned(bytes))
    }

    fn from_source(source: DataSource) -> std::io::Result<Self> {
        if source.len() < std::mem::size_of::<KHypHeader>() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "File too small",
            ));
        }

        let base_ptr = source.as_ptr();
        let header_ptr = base_ptr as *const KHypHeader;
        let header = unsafe { &*header_ptr };

        if &header.magic != b"KHYP" {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Invalid magic",
            ));
        }

        let table_offset = std::mem::size_of::<KHypHeader>();
        let table_ptr = unsafe { base_ptr.add(table_offset) } as *const KHypEntry;

        let table_bytes = header.table_size as usize * std::mem::size_of::<KHypEntry>();
        let pool_offset = table_offset + table_bytes;

        let pool_ptr = unsafe { base_ptr.add(pool_offset) };

        Ok(KHypDict {
            source,
            header: header_ptr,
            table: table_ptr,
            string_pool: pool_ptr,
            table_mask: header.table_size - 1,
        })
    }

    pub fn lookup<'a>(&'a self, word: &str) -> Option<&'a str> {
        let khash = crate::utils::djb2_hash(word.as_bytes());
        let mut idx = khash & self.table_mask;

        loop {
            let entry = unsafe { &*self.table.add(idx as usize) };
            if entry.key_offset == 0 {
                return None;
            }

            let key_bytes = self.get_pool_bytes(entry.key_offset);
            if key_bytes == word.as_bytes() {
                let val_bytes = self.get_pool_bytes(entry.val_offset);
                return std::str::from_utf8(val_bytes).ok();
            }
            idx = (idx + 1) & self.table_mask;
        }
    }

    pub fn get_pool_bytes(&self, offset: u32) -> &[u8] {
        unsafe {
            let ptr = self.string_pool.add(offset as usize);
            let mut len = 0;
            while *ptr.add(len) != 0 {
                len += 1;
            }
            std::slice::from_raw_parts(ptr, len)
        }
    }
}

unsafe impl Send for KHypDict {}
unsafe impl Sync for KHypDict {}
