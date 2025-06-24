# Porting C to Rust -- Guidelines.

# Writing good Rust C APIs

* The C interface exposed from Rust must be identical to the original interface.
* You must have an Rust implementation of _every_ function in the module.
* The Rust/C interface must be _safe_:
  - Don't return raw pointers to the C API, instead you must return a handle which is mapped to a Rust object.

Let's assume we have a C interface like:

```c
// dict.h

// opaque structure
typedef struct xmlDict;
xmlDict* xmlDictCreate(void);
void xmlDictFree(xmlDict* foo);
void xmlDictPrint(xmlDict* foo);
```

In Rust, this is naturally implemented as a HashMap:

```rust
// rust/src/dict/mod.rs
use std::sync::Arc;
use std::collections::HashMap;

/// String dictionary for string interning/deduplication
pub struct Dict {
    strings: HashMap<String, Arc<str>>,
    limit: Option<usize>,
}

impl Dict {
    /// Create a new dictionary
    pub fn new() -> Self {
        Self {
            strings: HashMap::new(),
            limit: None,
        }
    }

    pub fn print(&self) {
       println!("Dictionary: {} entries, {} bytes", self.size(), self.usage());
       if let Some(limit) = self.limit {
           println!("Limit: {} bytes", limit);
       }
       for (key, value) in &self.strings {
           println!("  '{}' -> {:p} (refs: {})", key, Arc::as_ptr(value), Arc::strong_count(value));
       }
   }
}

impl Default for Dict {
    fn default() -> Self {
        Self::new()
    }
}
```

## API Thunking

Now we want to expose our Rust functions back to C.  But instead of returning a
raw pointer, we must return a handle which is mapped to a Rust object. In this
case we'll use a HashMap thunk to map the C handles to Rust objects.

```rust
pub struct XmlDict {}
pub type XmlDictPtr = usize;

static DICTS: OnceLock<Mutex<
    HashMap<XmlDictPtr, Box<XmlDict>, BuildHasherDefault<DefaultHasher>>
>> = OnceLock::new();


#[no_mangle]
pub extern "C" fn xmlDictCreate() -> XmlDictPtr {
  let mutex = DICTS.get_or_init(|| {
      Mutex::new(HashMap::with_hasher(BuildHasherDefault::new()))
  });
  let mut m = mutex.lock().unwrap();
  let sz = m.len().try_into().unwrap();
  m.insert(sz, Box::new(XmlDict {}));
  return sz;
}

#[no_mangle]
pub extern "C" fn xmlDictFree(foo: XmlDictPtr) {
  let mutex = DICTS.get_or_init(|| {
      Mutex::new(HashMap::with_hasher(BuildHasherDefault::new()))
  });
  let mut m = mutex.lock().unwrap();
  m.remove(&foo);
}

#[no_mangle]
pub extern "C" fn xmlDictPrint(foo: XmlDictPtr) {
  let mutex = DICTS.get_or_init(|| {
      Mutex::new(HashMap::with_hasher(BuildHasherDefault::new()))
  });
  let m = mutex.lock().unwrap();
  let foo = m.get(&foo).expect(&format!("foo not found at index {} was it freed?", foo));
  foo.print();
}
```

This works well for opaque C structures; if the C structure is not opaque, we
need a different strategy. If our API returns by value or fills a value, we can
of course simply fill the appropriate fields in our call:

```rust
#[repr(C)]
pub struct XmlBar {
  pub x: i32,
  pub y: i32,
  pub z: xmlDictPtr,
}

#[no_mangle]
pub extern "C" fn xmlBarCreate(x: i32, y: i32, z: xmlDictPtr) -> XmlBarPtr {
  XmlBar { x, y, z }
}

// or equivalently - this is unsafe, but it's the only way to create a struct with a pointer to a C object.
#[no_mangle]
pub extern "C" fn xmlBarCreate(bar: &mut XmlBar) -> XmlBarPtr {
  bar.z = xmlDictCreate();
  bar.x = 0;
  bar.y = 0;
  bar
}

```

If our API is not exposed externally, then we can change our API itself to be
opaque, and for example switch to using accessor functions to access individual
fields:

```rust
#[no_mangle]
pub extern "C" fn xmlBarGetX(bar: XmlBarPtr) -> i32 {
  let mutex = DICTS.get_or_init(|| {
      Mutex::new(HashMap::with_hasher(BuildHasherDefault::new()))
  });
  let m = mutex.lock().unwrap();
  let bar = m.get(&bar).expect(&format!("bar not found at index {} was it freed?", bar));
  bar.x
}
```

