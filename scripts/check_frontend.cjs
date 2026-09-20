// Lexical references in JSX: catches missing hooks/components without a browser.
const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'..');
const babel=require(path.join(root,'assets/babel.js'));
const html=fs.readFileSync(path.join(root,'frontend/boss_app_source.html'),'utf8');
const code=html.match(/<script type="text\/babel">([\s\S]*?)<\/script>/)[1].replace('{% verbatim %}','').replace('{% endverbatim %}','');
const allowed=new Set(['React','ReactDOM','window','document','navigator','location','localStorage','sessionStorage','TextEncoder','AbortController','fetch','URL','Headers','FormData','File','Blob','FileReader','MediaRecorder','Audio','alert','confirm','prompt','console','setTimeout','clearTimeout','setInterval','clearInterval','requestAnimationFrame','cancelAnimationFrame','CustomEvent','DOMPurify','marked','atob','btoa','performance','URLSearchParams','Intl']);
const missing=new Set();
babel.transform(code,{presets:['react'],plugins:[()=>({visitor:{ReferencedIdentifier(p){if(!p.scope.hasBinding(p.node.name)&&!allowed.has(p.node.name))missing.add(p.node.name);}}})]});
if(missing.size){console.error('Unresolved references:',[...missing]);process.exit(1);}
console.log('JSX lexical references: passed');
