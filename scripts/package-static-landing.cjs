// Package the public pages only. No Next build, backend, credentials, or demo DB.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
const release = '20261107-pc-motion-1';
const source = path.join(root, 'frontend/public/landing');
const output = path.join(root, 'local-data/static-deploy-20261107/payload');
if (fs.existsSync(output)) throw new Error('Package already exists; do not overwrite a prepared release.');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const previousAuth = fs.readFileSync(path.join(root, 'local-data/static-deploy-20261107/auth-before.js'), 'utf8');
if (sha(Buffer.from(previousAuth)) !== '308e9fbf28c60eacd5f1fbd646441cfc3c31e11304bd9d5699ede0b514e9c005') throw new Error('Unexpected live authentication script.');
function tokens(text) {
  const parsed = ts.createSourceFile('auth.js', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  if (parsed.parseDiagnostics.length) throw new Error('Invalid authentication script.');
  const result = [];
  function visit(node) {
    const children = node.getChildren(parsed);
    if (children.length) children.forEach(visit);
    else if (node.kind !== ts.SyntaxKind.EndOfFileToken) result.push([node.kind, node.getText(parsed)]);
  }
  visit(parsed);
  return result;
}
const beforeTokens = tokens(previousAuth);
const afterTokens = tokens(fs.readFileSync(path.join(source, 'auth.js'), 'utf8'));
const copyKinds = new Set([ts.SyntaxKind.StringLiteral, ts.SyntaxKind.TemplateHead, ts.SyntaxKind.TemplateMiddle, ts.SyntaxKind.TemplateTail, ts.SyntaxKind.NoSubstitutionTemplateLiteral]);
if (beforeTokens.length !== afterTokens.length) throw new Error('Authentication logic changed.');
const copyChanges = [];
beforeTokens.forEach(([kind, value], index) => {
  const [nextKind, nextValue] = afterTokens[index];
  if (kind !== nextKind || (value !== nextValue && !copyKinds.has(kind))) throw new Error('Authentication logic differs at token ' + index);
  if (value !== nextValue) {
    if (!/[\u3000-\u9fff\uff00-\uffef]/u.test(nextValue)) throw new Error('Non-translation authentication change.');
    copyChanges.push({before:value, after:nextValue});
  }
});
const files = {};
function emit(relative, content) {
  const destination = path.join(output, relative);
  fs.mkdirSync(path.dirname(destination), {recursive:true});
  fs.writeFileSync(destination, content);
  files[relative] = {sha256:sha(content), bytes:Buffer.byteLength(content)};
}
const prefix = '/assets/' + release + '/';
const pages = fs.readdirSync(source).filter(name => name.endsWith('.html')).sort();
for (const name of pages) {
  let html = fs.readFileSync(path.join(source, name), 'utf8');
  html = html.replace(/\b(src|href)=(['"])([^'"\s]+)\2/g, (match, attribute, quote, value) => {
    const clean = value.split(/[?#]/)[0];
    if (/^[\w.-]+\.(css|js)$/.test(clean) || clean.startsWith('assets/')) {
      if (!fs.existsSync(path.join(source, clean))) throw new Error('Missing resource: ' + clean);
      return `${attribute}=${quote}${prefix}${clean}${quote}`;
    }
    return match;
  });
  html = html.replace('</head>', `<meta name="campusmate-static-release" content="${release}"></head>`);
  emit('pages/' + name, html);
}
for (const name of fs.readdirSync(source).filter(name => /\.(css|js)$/.test(name) && !name.startsWith('stellar.'))) {
  let content = fs.readFileSync(path.join(source, name), 'utf8');
  if (name.endsWith('.js')) new vm.Script(content, {filename:name});
  if (name.endsWith('.css')) content = content.replaceAll('/landing/assets/', prefix + 'assets/');
  emit('assets/' + release + '/' + name, content);
}
function copyAssets(dir, relative) {
  for (const entry of fs.readdirSync(dir, {withFileTypes:true})) {
    const from = path.join(dir, entry.name);
    const name = relative + '/' + entry.name;
    if (entry.isSymbolicLink()) throw new Error('Do not ship symlinks.');
    if (entry.isDirectory()) copyAssets(from, name);
    else emit('assets/' + release + '/' + name, fs.readFileSync(from));
  }
}
copyAssets(path.join(source, 'assets'), 'assets');
const manifest = {
  release,
  expectedAppRelease:'/opt/campusmate/releases/20261007-manual-attachment-notice-1',
  expectedBuildId:'CO-MFf0x9b59KwQFH6Jjv',
  expectedAuthHash:'308e9fbf28c60eacd5f1fbd646441cfc3c31e11304bd9d5699ede0b514e9c005',
  expectedIndexHash:'e71c7f3dbf2d6aeb82a491c03166ccb24a2857e49fc62241c9fda2b9256b8078',
  pages, files, authLogicIdentical:true, authTranslationChanges:copyChanges.length,
  notes:'Static public pages only; immutable URL assets; no service restart or backend deployment.'
};
fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2));
fs.copyFileSync(path.join(root, 'scripts/publish-static-landing.py'), path.join(output, 'publish.py'));
console.log(JSON.stringify({release, pages, files:Object.keys(files).length, bytes:Object.values(files).reduce((n,f)=>n+f.bytes,0), authLogicIdentical:true, translationChanges:copyChanges.length, output}));
