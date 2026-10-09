// Lexical references in JSX: catches missing hooks/components without a browser.
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');
const babel=require(path.join(root,'assets/babel.js'));
const allowed=new Set(['React','ReactDOM','window','document','navigator','location','history','PopStateEvent','localStorage','sessionStorage','TextEncoder','AbortController','fetch','URL','Headers','FormData','File','Blob','FileReader','MediaRecorder','Audio','alert','confirm','prompt','console','setTimeout','clearTimeout','setInterval','clearInterval','requestAnimationFrame','cancelAnimationFrame','CustomEvent','DOMPurify','marked','atob','btoa','performance','URLSearchParams','Intl','getComputedStyle']);

function frontendScript(html){
 const match=html.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
 if(!match)throw Error('Frontend Babel script was not found.');
 return match[1].replace('{% verbatim %}','').replace('{% endverbatim %}','');
}

function unresolvedReferences(code){
 const missing=new Set();
 babel.transform(code,{presets:['react'],plugins:[()=>({visitor:{ReferencedIdentifier(p){if(!p.scope.hasBinding(p.node.name)&&!allowed.has(p.node.name))missing.add(p.node.name);}}})]});
 return [...missing].sort();
}

if(require.main===module){
 const html=fs.readFileSync(path.join(root,'frontend/boss_app_source.html'),'utf8');
 const missing=unresolvedReferences(frontendScript(html));
 if(missing.length){console.error('Unresolved references:',missing);process.exitCode=1;}
 else console.log('JSX lexical references: passed');
}

module.exports={frontendScript,unresolvedReferences};
