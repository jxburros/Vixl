// Exercise the compiled plugin's import contract without a Figma login or file mutation.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const loadedFonts = new Set();
const created = [];
let completed;

function node(type) {
  const value = {
    type, name: '', children: [], x: 0, y: 0, width: 1, height: 1,
    fills: [], strokes: [], strokeWeight: 1, strokeAlign: 'CENTER', strokeCap: 'NONE', strokeJoin: 'MITER',
    cornerRadius: 0, dashPattern: [], relativeTransform: [[1, 0, 0], [0, 1, 0]],
    resize(w, h) { this.width = w; this.height = h; },
    appendChild(child) {
      if (child.parent) child.parent.children = child.parent.children.filter(item => item !== child);
      child.parent = this;
      this.children.push(child);
    },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(item => item !== this); },
    findAll(predicate) { return this.children.flatMap(child => [child, ...child.findAll(predicate)]).filter(predicate); },
    setRangeFontName(start, end, font) { assert(loadedFonts.has(JSON.stringify(font))); },
    setRangeFontSize() {}, setRangeLetterSpacing() {}, setRangeLineHeight() {}, setRangeTextDecoration() {},
    setRangeFills(start, end, fills) { this.lastRangeFill = fills; },
  };
  if (type === 'TEXT') {
    Object.defineProperty(value, 'characters', { get() { return this._characters || ''; },
      set(text) { assert(loadedFonts.has(JSON.stringify(this.fontName))); this._characters = text; } });
  }
  created.push(value);
  return value;
}
const figma = {
  currentPage: node('PAGE'), showUI() {},
  ui: { postMessage(message) { completed = message; } },
  createPage: () => node('PAGE'), createFrame: () => node('FRAME'), createText: () => node('TEXT'),
  createVector: () => node('VECTOR'), createRectangle: () => node('RECTANGLE'), createEllipse: () => node('ELLIPSE'),
  createNodeFromSvg(svg) {
    assert(svg.includes('viewBox="0 0 60 40"'));
    assert(svg.includes('M5 5'));
    const frame = node('FRAME'); frame.appendChild(node('VECTOR')); return frame;
  },
  group(children, parent) { const group = node('GROUP'); parent.appendChild(group); children.forEach(child => group.appendChild(child)); return group; },
  async loadFontAsync(font) { loadedFonts.add(JSON.stringify(font)); },
  async setCurrentPageAsync(page) { this.currentPage = page; },
  createImage(bytes) { assert(bytes.length > 0); return { hash: `image-${bytes.length}` }; },
  viewport: { scrollAndZoomIntoView() {} },
};
const context = vm.createContext({ figma, __html__: '', Uint8Array, console });
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
(async () => {
  await figma.ui.onmessage({ type: 'import', data: JSON.parse(fs.readFileSync(process.argv[3], 'utf8')) });
  assert.equal(completed.type, 'done', completed.message);
  const text = created.find(item => item.name === 'label');
  assert.equal(text.characters, 'Hello world');
  assert.equal(text.lastRangeFill[0].color.r, 1);
  assert.equal(text.lastRangeFill[0].color.g, 0);
  assert(created.find(item => item.name === 'photo').fills[0].imageHash);
  process.stdout.write(JSON.stringify(completed.report));
})().catch(error => { console.error(error); process.exitCode = 1; });
