use memmap2::Mmap;
use std::fs::File;

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
    pub fn load(path: &str) -> std::io::Result<Self> {
        let file = File::open(path)?;
        let mmap = unsafe { Mmap::map(&file)? };
        Self::from_source(DataSource::Mmap(mmap))
    }

    pub fn from_bytes(bytes: Vec<u8>) -> std::io::Result<Self> {
        Self::from_source(DataSource::Owned(bytes))
    }

    fn from_source(source: DataSource) -> std::io::Result<Self> {
        if source.len() < std::mem::size_of::<KDictHeader>() {
             return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "File too small"));
        }

        let base_ptr = source.as_ptr();
        let header_ptr = base_ptr as *const KDictHeader;
        let header = unsafe { &*header_ptr };

        if &header.magic != b"KDIC" {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "Invalid magic"));
        }

        let table_offset = std::mem::size_of::<KDictHeader>();
        // Check bounds would be good here
        let table_ptr = unsafe { base_ptr.add(table_offset) } as *const KDictEntry;
        
        let table_bytes = header.table_size as usize * std::mem::size_of::<KDictEntry>();
        let pool_offset = table_offset + table_bytes;
        
        if pool_offset > source.len() {
             return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "File truncated"));
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
        unsafe {
            self.string_pool.add(offset as usize)
        }
    }
}

unsafe impl Send for KDict {}
unsafe impl Sync for KDict {}
