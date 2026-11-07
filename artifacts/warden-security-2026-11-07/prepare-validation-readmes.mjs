// Restore frozen documentation first; change only suite-count tokens.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const sha=s=>createHash('sha256').update(s).digest('hex');
const rows=[];
for(const name of ['README.md','README-ru.md','README-es.md','README-fr.md','README-zh.md']){
 const original=readFileSync('/candidate/'+name,'utf8');
 const matches=original.match(/\b(?:1418|1517|1536)\b/g)??[];
 if(matches.length!==2)throw Error('Unexpected suite-count occurrences in '+name+':'+matches.length);
 const text=original.replace(/\b(?:1418|1517|1536)\b/g,'1536');
 writeFileSync('/work/warden/'+name,text);
 rows.push({name,replacements:matches.length,before:sha(original),after:sha(text),onlyCountTokensChanged:true});
}
writeFileSync('/results/readme-count-preparation.json',JSON.stringify(rows,null,2)+'\n');
console.log(JSON.stringify(rows));
