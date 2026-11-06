import { readFileSync, writeFileSync } from 'node:fs';
const source = readFileSync(new URL('../../sales/lion-elite-buildpipeline-sales-scripts.md', import.meta.url), 'utf8');
const sections = source.split(/^## /m).slice(1).map(section => ({title: section.slice(0, section.indexOf('\n')), body: section.slice(section.indexOf('\n') + 1).trim()}));
if (!sections.length) throw new Error('Sales playbook has no sections');
writeFileSync(new URL('../lib/sales-playbook.json', import.meta.url), JSON.stringify(sections) + '\n');
