"""Offline map of this research pass to the local ecosystem inventory."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASELINE=ROOT.parent/'external-links-2026-11-10/baseline/inventory.json'

def read(path):return json.loads(path.read_text())

def main():
    sources={
      'core':read(ROOT/'core/coverage.json')['components'],
      'agents-oracles':read(ROOT/'agents-oracles/coverage.json')['families'],
      'products':read(ROOT/'products/coverage.json')['families'],
      'root':read(ROOT/'root/coverage.json')}
    keys={'core':'component_id','agents-oracles':'family','products':'id','root':'component'}
    assignments={}
    def assign(branch,pairs):
        for component,families in pairs.items():assignments[component]=(branch,families.split(','))
    assign('core',{'aimarket-hub':'hub','aimarket-protocol':'protocol','aimarket-agent':'python-agent','aimarket-sdks':'sdk-typescript,sdk-dart,sdk-rust','aimarket-plugins':'plugins','aimarket-widget':'widget','aimarket-bridges':'bridges','ai-service-mesh':'service-mesh','acex':'acex','pulse-terminal':'pulse','escrow-signer':'escrow-signer','treasury':'treasury','aicom':'factory','aicom-products':'products'})
    assign('agents-oracles',{'metis':'metis','argus':'argus','hestia':'hestia','themis':'themis','hephaestus':'hephaestus','atlas':'atlas','gaia':'gaia','oracles':'oracles_platon','platon':'oracles_platon','aimarket-oracle-gateway':'oracle_gateway','aimarket-mcp':'mcp_gateway','momus':'momus','basanos':'basanos','dolos':'dolos','logos':'logos','skopos':'skopos'})
    assign('products',{'attested-memory':'attested-memory','attested':'attested-memory','cite-desks':'cite-desks','emberline':'cite-desks','domain-kit':'domain-operator-kit','esim-kit':'esim-operator-kit','pingblip':'pingblip','linkedin-profile-coach':'linkedin-coach','aimarket-desktop':'desktop','aicom-landing':'landing','aimarket-school':'school','aimarket-courses':'courses','create-aimarket-agent':'create-agent','aimarket-playground':'playground','use-cases-portal':'usecases'})
    assign('root',{'symmartys':'symmartys','helios':'helios','dioscuri':'dioscuri','theoros':'theoros','alien-monitor':'alien-monitor','signal-hunt':'signal-hunt','lottery':'lottery'})
    excluded={'profile':'Profile, not an independent component.','aicom-wiki':'Documentation mirror, not a separate product.','argus-wiki':'Documentation mirror, not a separate product.','histor':'Excluded by the user-directed focus on other components.','warden':'Excluded from this pass to avoid repeating the preceding security-centric search.','protocol-v2-from-spec-rs':'Local mapping declares github_published=false; same-editor reference implementation, not independent interoperability.','protocol-v2-receipt-from-spec':'Local mapping declares github_published=false; same-editor reference implementation.','protocol-v2-federator-go':'Local mapping declares github_published=false; same-editor reference implementation.'}
    matrix=[]
    for component in read(BASELINE)['components']:
        name=component['id'];row={'component_id':name,'repository':component.get('repository_target'),'mapped_repository_name':component['repo'],'homepage':component.get('homepage'),'publication_declared':component['github_published_declared'],'mapping_source':component['provenance']}
        if name in excluded:row.update(scope='excluded_or_reference',reason=excluded[name])
        else:
            assert name in assignments,name
            branch,families=assignments[name];refs=[]
            for family in families:
                matches=[i for i,r in enumerate(sources[branch]) if r[keys[branch]]==family];assert len(matches)==1,(branch,family)
                refs.append({'family':family,'coverage_file':f'{branch}/coverage.json','row_index':matches[0]})
            row.update(scope='bounded_family_search',branch=branch,evidence=refs,new_confirmed_runtime_integration=False,new_confirmed_independent_product_review=False)
            if name in ['attested','emberline']:row['alias_limit']='Covered with the parent family or historical alias; not counted as an independent product.'
        matrix.append(row)
    matrix.append({'component_id':'pantheon','scope':'supplementary_bounded_search','branch':'root','homepage':'https://pantheon.modelmarket.dev/','evidence':[{'family':'pantheon','coverage_file':'root/coverage.json','row_index':6}],'new_confirmed_runtime_integration':False,'new_confirmed_independent_product_review':False})
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'baseline':str(BASELINE.relative_to(ROOT.parent.parent)),'rows':matrix,'counts':dict(Counter(r['scope'] for r in matrix)),'limits':['Family rows preserve their actual query method and failed/not-executed requests.','A mapped row does not mean exhaustive code search for every child SKU or oracle.','Local declarations and aliases do not imply independently published products.']}
    followup=ROOT.parent/'external-matrix-gaps-2026-11-10/matrix-delta.json'
    if followup.exists():
        delta=read(followup)
        for row in matrix:
            notes=[r for r in delta['component_updates'] if r['component_id']==row['component_id']]
            if notes:row['latest_follow_up']={'delta_file':'../external-matrix-gaps-2026-11-10/matrix-delta.json','observed_at_utc':delta['generated_at_utc'],'records':notes}
        result['latest_follow_up']={'delta_file':'../external-matrix-gaps-2026-11-10/matrix-delta.json','historical_observations_preserved':True,'search_gaps_resolved':delta['search_gaps_resolved'],'remaining_access_gaps':delta['remaining_access_gaps']}
    (ROOT/'component-matrix.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    summary={'generated_at_utc':result['generated_at_utc'],'matrix_counts':result['counts'],'new_confirmed_external_runtime_integrations':0,'new_confirmed_independent_product_reviews':0,'new_confirmed_external_package_dependencies':0,'known_external_source_derivative':'https://github.com/th3artfuldodger/enterprise-factory','known_course_references':['https://github.com/EbookFoundation/free-programming-books/blob/main/courses/free-courses-en.md','https://thelearningstandard.org/news/how-autonomous-ai-agents-are-redefining-student-research-skills'],'internal_dependency_counts_do_not_sum_to_external_users':{'aimarket-hub':15,'aimarket-agent':1,'aimarket-oracle-core':20,'aimarket-momus':1},'coverage_files':[f'{branch}/coverage.json' for branch in sources],'findings_files':[f'{branch}/findings.json' for branch in sources],'status':'bounded_pass_complete_with_recorded_index_and_rate_limits'}
    if 'latest_follow_up' in result:summary['latest_follow_up']=result['latest_follow_up']
    (ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
