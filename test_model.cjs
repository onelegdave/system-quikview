const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const model = {};
vm.createContext(model);
vm.runInContext(fs.readFileSync(__dirname + '/Model.js', 'utf8'), model);
const igpu = {id:'0000:05:00.0',name:'Integrated',kind:'integrated',temp:61,usage:0};
const dgpu = {id:'0000:01:00.0',name:'Dedicated',kind:'dedicated',temp:45,usage:12};
const dgpu2 = {id:'0000:02:00.0',name:'Second dedicated',kind:'dedicated',temp:70,usage:25};
assert.equal(model.selectGpu([igpu,dgpu], 'auto', 'temp').id, dgpu.id);
assert.equal(model.selectGpu([igpu], 'auto', 'temp').id, igpu.id);
assert.equal(model.selectGpu([igpu,dgpu], 'integrated', 'temp').temp, 61);
assert.equal(model.selectGpu([igpu,dgpu], 'hottest', 'temp').id, igpu.id);
assert.equal(model.selectGpu([igpu,dgpu,dgpu2], dgpu2.id, 'temp').id, dgpu2.id);
assert.equal(model.selectGpu([dgpu2,igpu,dgpu], dgpu2.id, 'temp').id, dgpu2.id);
assert.equal(model.selectGpu([igpu], dgpu.id, 'temp'), null);
assert.equal(model.selectGpu([], 'auto', 'temp'), null);
assert.equal(model.selectGpu([{...dgpu,temp:null}], 'hottest', 'temp'), null);
assert.equal(model.selectGpu([igpu,{...dgpu,temp:null}], 'auto', 'temp').id, igpu.id);
assert.equal(model.selectGpu([igpu,{...dgpu,temp:null}], dgpu.id, 'temp').temp, null);
assert.equal(model.selectGpu([igpu], 'auto', 'usage').usage, 0);
const unknown = {...igpu,kind:'unknown'};
assert.equal(model.effectiveGpus([unknown], {[igpu.id]:'integrated'})[0].kind, 'integrated');
assert.equal(unknown.kind, 'unknown');
assert.match(model.sourceLabel('missing', []), /Disconnected/);
console.log('15 GPU source checks passed: single/multi/no GPU, missing sensors, stable identity, and role overrides.');
const sensors = [
    {chip:'nvme',device:'nvme0',label:'Composite',value:40},
    {chip:'nvme',device:'nvme1',label:'Composite',value:42},
    {chip:'amdgpu',device:igpu.id,label:'edge',value:60}
];
const groups = model.temperatureGroups(sensors,[igpu,dgpu]);
assert.equal(groups.length,4); // two disks, existing iGPU, added dGPU
assert.equal(groups.reduce((sum,g) => sum+g.sensors.length,0),4);
assert.equal(model.temperatureGroups([],[]).length,0);
assert.equal(model.temperatureState({value:95,maximum:85,critical:95}),'Critical');
assert.equal(model.temperatureState({value:85,maximum:85,critical:95}),'High');
assert.equal(model.temperatureState({value:95,maximum:null,critical:null}),'');
console.log('6 thermal grouping and hardware threshold checks passed.');
const available = [{key:'cpu'},{key:'memory'},{key:'gpu-a'},{key:'network'}];
const keys = list => Array.from(list, e => e.key);
assert.deepEqual(keys(model.orderedSections(['network','cpu','cpu','unplugged'],available)),['network','cpu','memory','gpu-a']);
assert.deepEqual(keys(model.orderedSections(null,available)),['cpu','memory','gpu-a','network']);
const moved = model.moveSection(['cpu','unplugged','memory','gpu-a','network'],available,'network',-1);
assert.deepEqual(Array.from(moved),['cpu','unplugged','memory','network','gpu-a']);
assert.equal(model.moveSection([],available,'cpu',-1),null);
assert.equal(model.moveSection([],available,'network',1),null);
assert.equal(model.moveSection([],available,'missing',1),null);
assert.deepEqual(keys(model.orderedSections(moved,available.concat([{key:'unplugged'}]))),['cpu','unplugged','memory','network','gpu-a']);
assert.equal(model.parsePalette('color6 = "#4ad9e0"\ncolor4 = "#6c7fe0" # comment').color6,'#4ad9e0');
assert.equal(model.parsePalette('color6 = "not-a-color"').color6,undefined);
console.log('9 layout ordering, reconnection, and palette parsing checks passed.');

assert.deepEqual(keys(model.orderedSections({0:"network",1:"cpu",length:2},available)),["network","cpu","memory","gpu-a"]);
console.log("Restored QML sequence ordering checked.");

assert.equal(model.parsePalette('cyan = "#179299"\nblue = "#1e66f5"\nyellow = "#df8e1d"').cyan, '#179299');
assert.equal(model.parsePalette('blue = "#1e66f5"').blue, '#1e66f5');
assert.equal(model.parsePalette('yellow = "#df8e1d"').yellow, '#df8e1d');
console.log("Stock named theme palette checked.");
