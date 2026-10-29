const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {marked} = require('/Users/alex/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/marked');
const dir = process.argv[2] || '/private/tmp/devto-localhost-auth-2026-10-28';
const raw = fs.readFileSync(path.join(dir, 'article.md'), 'utf8');
const title = raw.match(/^title: "(.*)"$/m)[1];
const body = marked.parse(raw.replace(/^---\n[\s\S]*?\n---\n/, ''));
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title>
<style>
*{box-sizing:border-box}body{margin:0;color:#252a2c;background:#f7f4ee;font:20px/1.75 Georgia,serif;-webkit-font-smoothing:antialiased}header,main{max-width:1100px;margin:auto;padding:0 46px}header{padding-top:62px;padding-bottom:30px}.eyebrow,.byline{font:13px/1.5 Arial,sans-serif;color:#62696b}.eyebrow{letter-spacing:.12em;text-transform:uppercase}h1{font:700 clamp(36px,4.7vw,60px)/1.08 Arial,sans-serif;letter-spacing:-.035em;max-width:1000px;margin:24px 0}.dek{font-size:22px;color:#62696b;max-width:800px}main>p,main>h2,main>ol,main>ul,main>pre,main>details,main>table{max-width:790px;margin-left:auto;margin-right:auto}main>p:has(img){max-width:none}img{display:block;width:100%;height:auto;border-radius:5px}h2{font:700 29px/1.25 Arial,sans-serif;letter-spacing:-.02em;margin-top:2.2em}a{color:#965316;text-underline-offset:3px}p:has(img)+p:has(em){max-width:950px;font:14px/1.6 Arial,sans-serif;color:#62696b}code{font:.82em/1.6 Menlo,Consolas,monospace;background:#e9e7e1;padding:2px 5px;border-radius:3px}pre{overflow-x:auto;background:#252a2c;color:#f4f0e8;border-radius:7px;padding:23px;font-size:15px}pre code{padding:0;background:none}details{border:1px solid #d4d0c8;border-radius:8px;padding:17px 20px}details pre{font-size:13px}summary{cursor:pointer;font:600 17px/1.5 Arial,sans-serif}table{width:100%;border-collapse:collapse;font:15px/1.6 Arial,sans-serif}td,th{padding:14px 12px;border-bottom:1px solid #d4d0c8;text-align:left;vertical-align:top}th{background:#ebe5db}td:first-child{width:42%}td code{overflow-wrap:anywhere}main>p:last-child{font:14px/1.7 Arial,sans-serif;color:#62696b;padding-top:25px;border-top:1px solid #d4d0c8;margin-top:35px}footer{text-align:center;font:12px/1.6 Arial,sans-serif;color:#62696b;padding:40px 20px 55px}@media(max-width:700px){header,main{padding-left:21px;padding-right:21px}header{padding-top:27px}body{font-size:18px}h1{font-size:37px}.dek{font-size:20px}pre{font-size:12px}table{font-size:12px}td,th{padding:10px 7px}details{padding:12px}details pre{font-size:11px}}
</style></head><body><header><div class="eyebrow">MCP · HTTP · Practical security</div><h1>${title}</h1><p class="dek">A local relay opens its own connection. Our HTTP RPC default now requires a credential, even when that connection comes from loopback.</p><p class="byline">Alex · 28 October 2026 · Local DEV.to draft</p></header><main>${body}</main><footer>Local editorial preview · Three illustrations · Code verified against the saved eight-request run</footer></body></html>`;
fs.writeFileSync(path.join(dir, 'preview.html'), html);
const codeBlocks = [...raw.matchAll(/```python\n([\s\S]*?)\n```/g)].map(m=>m[1]);
const demo = fs.readFileSync(path.join(__dirname,'localhost_auth_demo.py'),'utf8').trimEnd();
if(!codeBlocks.includes(demo)) throw new Error('Embedded demonstration differs from verified file');
const imageRefs = [...raw.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)].map(m=>m[1]);
for(const rel of imageRefs) if(!fs.existsSync(path.join(dir,rel))) throw new Error(`Missing image: ${rel}`);
if(imageRefs.length!==3) throw new Error('Expected three figures');
const validation={embedded_demo_exact:true,images:imageRefs,frontmatter_published:false,code_sha256:crypto.createHash('sha256').update(demo+'\n').digest('hex'),article_sha256:crypto.createHash('sha256').update(raw).digest('hex')};
fs.writeFileSync(path.join(__dirname,'article-validation.json'),JSON.stringify(validation,null,2)+'\n');
console.log(JSON.stringify(validation));
