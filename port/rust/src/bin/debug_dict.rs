use khmer_segmenter::kdict::KDict;

fn main() {
    let kdict = KDict::load("port/common/khmer_dictionary.kdict").unwrap();
    let header = unsafe { &*kdict.header };
    let magic = std::str::from_utf8(&header.magic).unwrap_or("INVALID");
    let num_entries = header.num_entries;
    let table_size = header.table_size;
    let default_cost = header.default_cost;
    let unknown_cost = header.unknown_cost;
    let max_word_length = header.max_word_length;

    println!("Magic: {:?}", magic);
    println!("Num Entries: {}", num_entries);
    println!("Table Size: {}", table_size);
    println!("Default Cost: {}", default_cost);
    println!("Unknown Cost: {}", unknown_cost);
    println!("Max Word Length: {}", max_word_length);
}
