import test from 'node:test';
import assert from 'node:assert/strict';
import {plan,numberOf,columnIndex,quotedTab} from '../public/match.js';
const cfg={no:'A',pic:'D',link:'G',person:'afzal',start:8};
test('matches content number, PIC, and actual row rather than row number',()=>{
 const result=plan([['7','','','afzal'],['11','','','kayla'],['11','','',' AFZAL ']],['11 - VLC','7'],cfg);
 assert.deepEqual(result.map(x=>[x.row,x.error]),[[10,''],[8,'']]);
});
test('protects populated links and rejects ambiguous numbers',()=>{
 assert.match(plan([['7','','','afzal','','','https://existing']],['7'],cfg)[0].error,/sudah terisi/);
 assert.match(plan([['7','','','afzal'],['7','','','afzal']],['7'],cfg)[0].error,/ambigu/);
 assert.ok(plan([['7','','','afzal']],['7','07 - other'],cfg).every(x=>x.error));
});
test('ignores other PICs and unmatched numbers',()=>{
 assert.ok(plan([['11','','','dinda']],['11'],cfg)[0].error);
 assert.ok(plan([],['bad'],cfg)[0].error);
});
test('parses strict numeric prefixes and validates column names',()=>{
 assert.equal(numberOf('011 - VLC'),'11');assert.equal(numberOf('11abc'),null);
 assert.equal(columnIndex('AA'),26);assert.throws(()=>columnIndex('A1'));
 assert.equal(quotedTab("Afzal's"),"'Afzal''s'");
});
