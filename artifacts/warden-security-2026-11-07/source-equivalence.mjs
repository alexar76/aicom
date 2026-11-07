// Compare the active frozen detector with a documentation-count validation copy.
import {readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
const [left,right,destination]=process.argv.slice(2);
const sha=b=>createHash('sha256').update(b).digest('hex');
function tree(root){const result={};function visit(dir){for(const e of readdirSync(dir,{withFileTypes:true}).sort((a,b)=>a.name<b.name?-1:a.name>b.name?1:0)){if(e.name==='node_modules'||e.name==='.git')continue;const p=join(dir,e.name);if(e.isDirectory())visit(p);else if(e.isFile())result[p.slice(root.length+1)]=sha(readFileSync(p))}}visit(root);return result}
const a=tree(left),b=tree(right),allowed=new Set(['README.md','README-ru.md','README-es.md','README-fr.md','README-zh.md']);
const countNormalized=text=>text.replace(/\b(?:1418|1517|1536)\b/g,'<TEST_COUNT>');
const differences=[...new Set([...Object.keys(a),...Object.keys(b)])].sort().filter(k=>a[k]!==b[k]).map(file=>({file,frozen:a[file]??null,validation:b[file]??null,permittedDocumentationCountChange:allowed.has(file)&&!!a[file]&&!!b[file]&&countNormalized(readFileSync(join(left,file),'utf8'))===countNormalized(readFileSync(join(right,file),'utf8'))}));
const runtimeFiles=Object.keys(a).filter(k=>k.startsWith('src/')||k.startsWith('dist/')||k.startsWith('test/')||k.startsWith('scripts/')||['package.json','package-lock.json','tsconfig.json','vitest.config.ts','server.json','action.yml','.pre-commit-hooks.yaml'].includes(k));
const runtimeManifest=Object.fromEntries(runtimeFiles.sort().map(k=>[k,a[k]]));
const result={at:new Date().toISOString(),frozenFiles:Object.keys(a).length,validationFiles:Object.keys(b).length,runtimeFiles:runtimeFiles.length,runtimeIdentitySha256:sha(JSON.stringify(runtimeManifest)),differences,onlyFiveReadmeFilesMayDiffer:differences.every(d=>d.permittedDocumentationCountChange),runtimeFilesEqual:runtimeFiles.every(k=>a[k]===b[k])};
result.passed=result.onlyFiveReadmeFilesMayDiffer&&result.runtimeFilesEqual;
writeFileSync(destination,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));process.exitCode=result.passed?0:1;
