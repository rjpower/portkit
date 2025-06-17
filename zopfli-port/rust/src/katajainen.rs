
use libc::{c_int, c_uint, size_t};
use std::ptr;
use std::slice;

#[derive(Clone, Copy, Debug)]
struct Node {
    weight: size_t,
    tail: *mut Node,
    count: i32,
}

struct NodePool {
    next: *mut Node,
}

fn init_node(weight: size_t, count: i32, tail: *mut Node, node: *mut Node) {
    unsafe {
        (*node).weight = weight;
        (*node).count = count;
        (*node).tail = tail;
    }
}

fn boundary_pm(
    lists: &mut [[*mut Node; 2]],
    leaves: &mut [Node],
    numsymbols: i32,
    pool: &mut NodePool,
    index: i32,
) {
    unsafe {
        let lastcount = (*lists[index as usize][1]).count;

        if index == 0 && lastcount >= numsymbols {
            return;
        }

        let newchain = pool.next;
        pool.next = pool.next.add(1);
        let oldchain = lists[index as usize][1];

        lists[index as usize][0] = oldchain;
        lists[index as usize][1] = newchain;

        if index == 0 {
            init_node(
                leaves[lastcount as usize].weight,
                lastcount + 1,
                ptr::null_mut(),
                newchain,
            );
        } else {
            let sum = (*lists[(index - 1) as usize][0]).weight + (*lists[(index - 1) as usize][1]).weight;
            if lastcount < numsymbols && sum > leaves[lastcount as usize].weight {
                init_node(
                    leaves[lastcount as usize].weight,
                    lastcount + 1,
                    (*oldchain).tail,
                    newchain,
                );
            } else {
                init_node(sum, lastcount, lists[(index - 1) as usize][1], newchain);
                boundary_pm(lists, leaves, numsymbols, pool, index - 1);
                boundary_pm(lists, leaves, numsymbols, pool, index - 1);
            }
        }
    }
}

fn boundary_pm_final(
    lists: &mut [[*mut Node; 2]],
    leaves: &mut [Node],
    numsymbols: i32,
    pool: &mut NodePool,
    index: i32,
) {
    unsafe {
        let lastcount = (*lists[index as usize][1]).count;
        let sum = (*lists[(index - 1) as usize][0]).weight + (*lists[(index - 1) as usize][1]).weight;

        if lastcount < numsymbols && sum > leaves[lastcount as usize].weight {
            let newchain = pool.next;
            let oldchain = (*lists[index as usize][1]).tail;
            lists[index as usize][1] = newchain;
            (*newchain).count = lastcount + 1;
            (*newchain).tail = oldchain;
        } else {
            (*lists[index as usize][1]).tail = lists[(index - 1) as usize][1];
        }
    }
}


fn extract_bit_lengths(chain: *mut Node, leaves: &[Node], bitlengths: &mut [u32]) {
    let mut counts = [0; 16];
    let mut end = 16;
    let mut ptr = 15;
    let mut value = 1;
    let mut node = chain;

    while !node.is_null() {
        end -= 1;
        unsafe {
            counts[end] = (*node).count;
            node = (*node).tail;
        }
    }

    let mut val = counts[15];
    while ptr >= end {
        while val > counts[ptr - 1] {
            unsafe {
                if val - 1 < leaves.len() as i32 {
                    bitlengths[(*leaves.get_unchecked(val as usize - 1)).count as usize] = value;
                }
            }
            val -= 1;
        }
        ptr -= 1;
        value += 1;
    }
}

pub fn ZopfliLengthLimitedCodeLengths(
    frequencies: *const size_t,
    n: c_int,
    maxbits: c_int,
    bitlengths_ptr: *mut c_uint,
) -> c_int {
    let freqs = unsafe { slice::from_raw_parts(frequencies, n as usize) };
    let bitlengths = unsafe { slice::from_raw_parts_mut(bitlengths_ptr, n as usize) };

    bitlengths.iter_mut().for_each(|m| *m = 0);

    let mut leaves: Vec<Node> = freqs
        .iter()
        .enumerate()
        .filter(|(_, &f)| f > 0)
        .map(|(i, &f)| Node {
            weight: f,
            count: i as i32,
            tail: ptr::null_mut(),
        })
        .collect();

    let numsymbols = leaves.len();

    // Match C behavior: (1 << maxbits) < numsymbols
    // In C, when maxbits >= 32, the behavior is undefined but typically
    // shifts by (maxbits % 32) due to the x86/ARM shift instruction behavior
    let effective_shift = maxbits % 32;
    let shifted_value = if effective_shift == 0 {
        1i32  // 1 << 0 = 1
    } else {
        1i32 << effective_shift
    };
    
    if shifted_value < numsymbols as i32 {
        return 1;
    }
    if numsymbols == 0 {
        return 0;
    }
    if numsymbols == 1 {
        if !leaves.is_empty() && (leaves[0].count as usize) < bitlengths.len() {
            bitlengths[leaves[0].count as usize] = 1;
        }
        return 0;
    }
    if numsymbols == 2 {
        if leaves.len() > 1 && (leaves[0].count as usize) < bitlengths.len() && (leaves[1].count as usize) < bitlengths.len() {
            bitlengths[leaves[0].count as usize] += 1;
            bitlengths[leaves[1].count as usize] += 1;
        }
        return 0;
    }
    
    for leaf in &mut leaves {
        if leaf.weight >= (1 << (std::mem::size_of::<size_t>() * 8 - 9)) {
            return 1;
        }
        leaf.weight = (leaf.weight << 9) | leaf.count as size_t;
    }

    leaves.sort_by_key(|k| k.weight);

    for leaf in &mut leaves {
        leaf.weight >>= 9;
    }

    let mut maxbits_mut = maxbits;
    if numsymbols - 1 < maxbits_mut as usize {
        maxbits_mut = (numsymbols - 1) as i32;
    }

    // Check for overflow in node allocation calculation
    let nodes_count = maxbits_mut.saturating_mul(2).saturating_mul(numsymbols as i32);
    if nodes_count < 0 || nodes_count > 10000000 {  // reasonable limit
        return 1;
    }

    let mut nodes_vec: Vec<Node> =
        vec![
            Node {
                weight: 0,
                count: 0,
                tail: ptr::null_mut()
            };
            nodes_count as usize
        ];
    let mut pool = NodePool {
        next: nodes_vec.as_mut_ptr(),
    };

    let mut lists: Vec<[*mut Node; 2]> = vec![[ptr::null_mut(); 2]; maxbits_mut as usize];

    if numsymbols > 1 {
        unsafe {
            let node0 = pool.next;
            pool.next = pool.next.add(1);
            let node1 = pool.next;
            pool.next = pool.next.add(1);
            init_node(leaves[0].weight, 1, ptr::null_mut(), node0);
            init_node(leaves[1].weight, 2, ptr::null_mut(), node1);

            for i in 0..maxbits_mut as usize {
                lists[i][0] = node0;
                lists[i][1] = node1;
            }
        }
    }


    let num_boundary_pm_runs = 2 * numsymbols - 4;
    for i in 0..num_boundary_pm_runs {
        if i < num_boundary_pm_runs -1 {
            boundary_pm(
                &mut lists,
                &mut leaves,
                numsymbols as i32,
                &mut pool,
                maxbits_mut - 1,
            );
        } else {
            boundary_pm_final(
                &mut lists,
                &mut leaves,
                numsymbols as i32,
                &mut pool,
                maxbits_mut - 1,
            );
        }
    }
    
    if maxbits_mut > 0 {
        extract_bit_lengths(lists[(maxbits_mut - 1) as usize][1], &leaves, bitlengths);
    }
    0
}
