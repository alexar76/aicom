use glib::{prelude::*, Variant};
fn strings() -> Variant { ["zero", "αβ", "", "last"].to_variant() }
#[test]
fn next_and_back_preserve_contents_and_bounds() {
    let value = strings(); let mut iter=value.array_iter_str().unwrap();
    assert_eq!(iter.len(),4);assert_eq!(iter.next(),Some("zero"));assert_eq!(iter.next_back(),Some("last"));
    assert_eq!(iter.next(),Some("αβ"));assert_eq!(iter.next_back(),Some(""));assert_eq!(iter.next(),None);assert_eq!(iter.next_back(),None);
}
#[test]
fn nth_nth_back_and_last_work_in_optimized_build() {
    let value=strings();assert_eq!(value.array_iter_str().unwrap().nth(1),Some("αβ"));
    assert_eq!(value.array_iter_str().unwrap().nth_back(1),Some(""));assert_eq!(value.array_iter_str().unwrap().last(),Some("last"));
    assert_eq!(value.array_iter_str().unwrap().nth(usize::MAX),None);assert_eq!(value.array_iter_str().unwrap().nth_back(usize::MAX),None);
}
#[test]
fn empty_and_non_string_variants_are_handled() {
    let empty:Vec<String>=Vec::new();let value=empty.to_variant();assert_eq!(value.array_iter_str().unwrap().next(),None);
    assert!(42_i32.to_variant().array_iter_str().is_err());
}
