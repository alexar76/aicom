"""Append recoveries to the prior matrix without rewriting historical observations."""
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    for file in ['acex/coverage.json','pulse-escrow/coverage.json','recovery/findings.json']:
        json.loads((ROOT/file).read_text())
    root=json.loads((ROOT/'root/findings.json').read_text())
    bykey={r['key']:r for r in root['searches']}
    updates=[]
    scopes={
      'acex':['readme-acex','imports-acex','contract-audit-pool','contract-listing','config-jupiter'],
      'pulse-terminal':['readme-pulse','url-pulse'],
      'escrow-signer':['readme-escrow','config-escrow'],
      'treasury':['readme-treasury']}
    for component,keys in scopes.items():
        rows=[bykey[k] for k in keys]
        assert all(r['status']==200 and r['total_count']==0 and r['incomplete_results'] is False for r in rows)
        updates.append({'component_id':component,'status':'previous_native_readme_gap_resolved_no_candidates','observed_at_utc':max(r['observed_at_utc'] for r in rows),'source_captures':[{'key':r['key'],'url':r['url'],'body':'root/'+r['evidence'],'status':200,'total_count':0,'incomplete_results':False} for r in rows],'new_confirmed_foreign_import_api_call_or_config':False,'remaining_scope_limit':'README/commit messages only; full code search and private or unindexed clients remain unknown.'})
    for component,status,notes in [
      ('aimarket-courses','primary_publisher_content_recovered','Official GitHub web PR13394 and pinned commit read; historical portal-link curation, not a new runtime use or new listing.'),
      ('attested-memory','primary_publisher_content_recovered_and_candidate_examined','APIs.io literal published YAML read at artifacts.apis.io; generated registry harvest. Obsidian README plus linked raw/compiled example have no unique ecosystem markers.'),
      ('attested','family_recovery_reference','See attested-memory family recovery; wrapper not a separate integration.'),
      ('esim-kit','public_source_still_challenge_blocked','Socket ordinary one-shot GET still403 managed challenge; source remains unread.'),
      ('aicom','public_source_still_challenge_blocked','UNDERCODE ordinary one-shot GET still403 managed challenge; no fresh reading or new review.')]:
        updates.append({'component_id':component,'status':status,'notes':notes,'evidence_file':'recovery/findings.json','new_confirmed_foreign_import_api_call_or_config':False})
    delta={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'baseline_matrix':'../external-components-2026-11-10/component-matrix.json','component_updates':updates,'search_gaps_resolved':4,'search_requests_completed':10,'new_confirmed_foreign_import_api_call_or_config':0,'github_core_api_restored':False,'remaining_access_gaps':['GitHub CORE REST quota: one repeat403; same-source public pages were read separately.','UNDERCODE and Socket managed challenges remain403.','grep.app normal one-shot retry429; no complete code-index negative evidence.'],'evidence_files':['root/findings.json','acex/coverage.json','pulse-escrow/coverage.json','recovery/findings.json']}
    (ROOT/'matrix-delta.json').write_text(json.dumps(delta,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in delta.items() if k!='component_updates'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
