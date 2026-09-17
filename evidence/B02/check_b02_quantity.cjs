const fs = require('fs');
const vm = require('vm');
const crypto = require('crypto');
const oldPath = '/workspace/sites/bos-original-refined/frontend/boss_app_source.html';
const newPath = '/workspace/scratch/c7b51e996a9f/tmp/b02_ui_candidate/frontend/boss_app_source.html';
const old = fs.readFileSync(oldPath, 'utf8');
const fresh = fs.readFileSync(newPath, 'utf8');
const expression = old.match(/quantity:(String\(Number\(r\.quantity\)-Number\(r\.received\)\))/);
if (!expression) throw Error('Original receive quantity expression not found');
const functionSource = fresh.match(/function purchaseRemaining\(quantity,received\)\{[\s\S]+?\n\}/)?.[0];
if (!functionSource) throw Error('Candidate quantity function not found');
const oldValue = vm.runInNewContext(expression[1], {r:{quantity:'0.300',received:'0.200'}});
const resolve = vm.runInNewContext('(' + functionSource + ')');
const cases = [
  ['0.300','0.200','0.100'],
  ['5.000','2.000','3.000'],
  ['0.001','0.000','0.001'],
  ['2.125','1.875','0.250'],
  ['999999999.999','0.001','999999999.998'],
  ['1','1','0.000']
].map(([quantity,received,expected]) => ({quantity,received,expected,actual:resolve(quantity,received)}));
for (const test of cases) if (test.actual !== test.expected) throw Error(JSON.stringify(test));
let impossibleRejected = false;
try { resolve('1.000','1.001'); } catch { impossibleRejected = true; }
if (!impossibleRejected || oldValue === '0.100') throw Error('Regression oracle failed');
console.log(JSON.stringify({
  scope:'Actual extracted JavaScript source execution in Node; not browser or server acceptance',
  before:{expression:expression[1],quantity:'0.300',received:'0.200',expected:'0.100',actual:oldValue,passed:false},
  after:{source_sha256:crypto.createHash('sha256').update(fresh).digest('hex'),cases,impossibleRejected,passed:true}
},null,2));
