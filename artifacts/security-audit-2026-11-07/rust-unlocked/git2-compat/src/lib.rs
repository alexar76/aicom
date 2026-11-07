pub fn reachable_commit_count(repo_path: &str) -> Result<u64, String> {
    let repo = git2::Repository::open(repo_path)
        .map_err(|e| format!("Cannot open git repo at {}: {}", repo_path, e))?;
    let mut revwalk = repo.revwalk().map_err(|e| e.to_string())?;
    revwalk.push_head().map_err(|e| e.to_string())?;
    Ok(revwalk.count() as u64)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn counts_commits_in_disposable_local_repo() {
        let path = std::env::temp_dir().join(format!("aicom-git2-local-test-{}", std::process::id()));
        assert!(!path.exists());
        let repo = git2::Repository::init(&path).unwrap();
        let mut index = repo.index().unwrap();
        let oid = index.write_tree().unwrap();
        let tree = repo.find_tree(oid).unwrap();
        let sig = git2::Signature::now("Disposable audit fixture", "fixture@example.invalid").unwrap();
        repo.commit(Some("HEAD"), &sig, &sig, "local fixture", &tree, &[]).unwrap();
        assert_eq!(reachable_commit_count(path.to_str().unwrap()).unwrap(), 1);
        drop(tree); drop(index); drop(repo);
        std::fs::remove_dir_all(&path).unwrap();
    }
    #[test]
    fn refuses_missing_repository() {
        let path = std::env::temp_dir().join(format!("aicom-git2-missing-{}", std::process::id()));
        assert!(!path.exists());
        assert!(reachable_commit_count(path.to_str().unwrap()).unwrap_err().contains("Cannot open git repo"));
    }
}
