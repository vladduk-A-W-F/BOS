/* TEST-INFRA-LEXICAL-01: canaries exercise the actual lexical analyzer. */
const assert=require('assert');
const {unresolvedReferences}=require('../check_frontend.cjs');
let checks=0;
function check(label,fn){fn();checks++;console.log('PASS '+label);}

check('permits browser getComputedStyle only as a known global',()=>{
 assert.deepEqual(unresolvedReferences('const node={}; getComputedStyle(node);'),[]);
});
check('still reports an unknown function',()=>{
 assert.deepEqual(unresolvedReferences('unknownFunction();'),['unknownFunction']);
});
check('still reports an unknown JSX component and identifier typo',()=>{
 assert.deepEqual(unresolvedReferences('const view=<MissingComponent />; useStte();'),['MissingComponent','useStte']);
});
check('still throws for JSX syntax errors',()=>{
 assert.throws(()=>unresolvedReferences('const view=<BrokenComponent>'),/SyntaxError|Unexpected token|Unterminated JSX/);
});

console.log(JSON.stringify({result:'PASS',checks,scope:'actual lexical analyzer canaries; no browser, build, or product suite'},null,2));
