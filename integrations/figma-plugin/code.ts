// This plugin imports the documented vixl-figma-1 interchange, entirely offline.
type RecordData = { [key: string]: any };
type ImportReport = { substitutions: string[]; warnings: string[]; pages: number };

figma.showUI(__html__, { width: 420, height: 360, themeColors: true });

function matrixMultiply(a: Transform, b: Transform): Transform {
  return [
    [a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1],
      a[0][0] * b[0][2] + a[0][1] * b[1][2] + a[0][2]],
    [a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1],
      a[1][0] * b[0][2] + a[1][1] * b[1][2] + a[1][2]],
  ];
}

function decodeBase64(text: string): Uint8Array {
  if (text.length > 89478488 || text.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(text)) {
    throw new Error("Invalid embedded image or image larger than 64 MB");
  }
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const padding = text.endsWith("==") ? 2 : text.endsWith("=") ? 1 : 0;
  const result = new Uint8Array(text.length / 4 * 3 - padding);
  let out = 0;
  for (let index = 0; index < text.length; index += 4) {
    const value = (alphabet.indexOf(text[index]) << 18) | (alphabet.indexOf(text[index + 1]) << 12)
      | (Math.max(0, alphabet.indexOf(text[index + 2])) << 6) | Math.max(0, alphabet.indexOf(text[index + 3]));
    for (const shift of [16, 8, 0]) {
      if (out < result.length) result[out++] = (value >> shift) & 255;
    }
  }
  return result;
}

function validateDocument(data: RecordData): void {
  if (data.format !== "vixl-figma-1" || data.document?.type !== "DOCUMENT"
      || !Array.isArray(data.document.children) || !data.document.children.length
      || data.document.children.length > 500 || Object.keys(data.images || {}).length > 200) {
    throw new Error("Choose a Vixl .figma.json export (format vixl-figma-1)");
  }
  let count = 0;
  function visit(node: RecordData, depth: number): void {
    if (++count > 20000 || depth > 32) throw new Error("The file has too many nodes or nested groups");
    if (!node || typeof node.name !== "string") throw new Error("Invalid node name");
    if (node.type === "CANVAS") {
      if (depth !== 0) throw new Error("Pages must be at the document root");
    } else {
      if (!["FRAME", "GROUP", "RECTANGLE", "ELLIPSE", "LINE", "VECTOR", "TEXT"].includes(node.type)) {
        throw new Error(`Unsupported node type ${node.type}`);
      }
      const size = node.size;
      if (!size || !Number.isFinite(size.x) || !Number.isFinite(size.y) || size.x <= 0 || size.y <= 0) {
        throw new Error(`Invalid size for ${node.name}`);
      }
      const transform = node.relativeTransform;
      if (!Array.isArray(transform) || transform.length !== 2
          || transform.some((row: number[]) => !Array.isArray(row) || row.length !== 3 || !row.every(Number.isFinite))) {
        throw new Error(`Invalid transform for ${node.name}`);
      }
    }
    if (node.children !== undefined && !Array.isArray(node.children)) throw new Error("Invalid children list");
    for (const child of node.children || []) visit(child, depth + 1);
  }
  for (const page of data.document.children) {
    if (page.type !== "CANVAS") throw new Error("Document children must be pages");
    visit(page, 0);
  }
}

async function importDocument(data: RecordData): Promise<ImportReport> {
  validateDocument(data);
  const report: ImportReport = { substitutions: [], warnings: [], pages: 0 };
  const images: { [key: string]: string } = {};
  let imageBytes = 0;
  for (const ref of Object.keys(data.images || {})) {
    const record = data.images[ref];
    if (record.mime !== "image/png" || typeof record.base64 !== "string") throw new Error("Invalid image record");
    const bytes = decodeBase64(record.base64);
    imageBytes += bytes.length;
    if (imageBytes > 268435456) throw new Error("Embedded images exceed 256 MB");
    images[ref] = figma.createImage(bytes).hash;
  }
  function paints(records: RecordData[] = []): Paint[] {
    return records.map((paint: RecordData): Paint => {
      if (paint.type === "IMAGE") {
        if (!images[paint.imageRef]) throw new Error(`Missing image ${paint.imageRef}`);
        return { type: "IMAGE", imageHash: images[paint.imageRef], scaleMode: "FILL" };
      }
      if (paint.type === "SOLID") return { type: "SOLID", color: paint.color, opacity: paint.opacity ?? 1 };
      if (paint.type === "GRADIENT_LINEAR" || paint.type === "GRADIENT_RADIAL") {
        return { type: paint.type, gradientTransform: paint.gradientTransform, gradientStops: paint.gradientStops };
      }
      throw new Error(`Unsupported paint ${paint.type}`);
    });
  }
  const fonts = new Map<string, FontName>();
  async function font(style: RecordData, name: string): Promise<FontName> {
    const wanted = { family: style.fontFamily || "Inter", style: style.fontStyle || "Regular" };
    const key = JSON.stringify(wanted);
    const cached = fonts.get(key);
    if (cached) return cached;
    let selected = wanted;
    try {
      await figma.loadFontAsync(wanted);
    } catch {
      selected = { family: "Inter", style: "Regular" };
      await figma.loadFontAsync(selected);
      report.substitutions.push(`${name}: ${wanted.family} ${wanted.style} → Inter Regular`);
    }
    fonts.set(key, selected);
    return selected;
  }
  async function textNode(source: RecordData): Promise<TextNode> {
    const node = figma.createText();
    const style = source.style || {};
    node.fontName = await font(style, source.name);
    node.fontSize = style.fontSize || 16;
    node.characters = source.characters || "";
    node.textAlignHorizontal = style.textAlignHorizontal || "LEFT";
    node.textAlignVertical = style.textAlignVertical || "TOP";
    node.letterSpacing = { unit: "PIXELS", value: style.letterSpacing || 0 };
    if (style.lineHeightPx) node.lineHeight = { unit: "PIXELS", value: style.lineHeightPx };
    if (style.paragraphSpacing !== undefined) node.paragraphSpacing = style.paragraphSpacing;
    const overrides: number[] = source.characterStyleOverrides || [];
    for (let start = 0; start < Math.min(overrides.length, node.characters.length);) {
      let end = start + 1;
      while (end < overrides.length && overrides[end] === overrides[start]) end++;
      end = Math.min(end, node.characters.length);
      const range = (source.styleOverrideTable || {})[String(overrides[start])];
      if (range) {
        node.setRangeFontName(start, end, await font({ ...style, ...range }, source.name));
        if (range.fontSize) node.setRangeFontSize(start, end, range.fontSize);
        if (range.letterSpacing !== undefined) node.setRangeLetterSpacing(start, end, { unit: "PIXELS", value: range.letterSpacing });
        if (range.lineHeightPx !== undefined) node.setRangeLineHeight(start, end, { unit: "PIXELS", value: range.lineHeightPx });
        if (range.fills) node.setRangeFills(start, end, paints(range.fills));
        if (range.textDecoration) node.setRangeTextDecoration(start, end, range.textDecoration);
      }
      start = end;
    }
    return node;
  }
  async function emit(source: RecordData, parent: PageNode | FrameNode): Promise<SceneNode> {
    let node: SceneNode;
    let vectorGeometry: SceneNode[] | undefined;
    let groupOrigin: Transform = [[1, 0, 0], [0, 1, 0]];
    if (source.type === "TEXT") node = await textNode(source);
    else if (source.type === "ELLIPSE") node = figma.createEllipse();
    else if (source.type === "VECTOR") {
      const escape = (text: string) => text.replace(/&/g, "&amp;").replace(/"/g, "&quot;")
        .replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const paths = (source.fillGeometry || []).map((path: RecordData) =>
        `<path d="${escape(path.path)}" fill="black" stroke="black" stroke-width="1" fill-rule="${path.windingRule === "EVENODD" ? "evenodd" : "nonzero"}"/>`).join("");
      const frame = figma.createNodeFromSvg(`<svg xmlns="http://www.w3.org/2000/svg" width="${source.size.x}" height="${source.size.y}" viewBox="0 0 ${source.size.x} ${source.size.y}">${paths}</svg>`);
      // The SVG viewport retains path margins and open endpoints. Resizing the vector itself
      // would stretch its ink bounds to the entire declared layer box.
      vectorGeometry = frame.findAll(child => "fills" in child && child.type !== "FRAME");
      node = frame;
    } else if (source.type === "LINE") {
      const vector = figma.createVector();
      vector.vectorPaths = [{ windingRule: "NONZERO", data: `M0 0 L${source.size.x} ${source.size.y}` }];
      node = vector;
    } else if (source.type === "FRAME" || source.type === "GROUP") node = figma.createFrame();
    else node = figma.createRectangle();
    parent.appendChild(node);
    node.name = source.name;
    node.resize(source.size.x, source.size.y);
    for (const geometry of vectorGeometry || [node]) {
      if ("fills" in geometry) geometry.fills = paints(source.fills);
      if ("strokes" in geometry) geometry.strokes = paints(source.strokes);
      if ("strokeWeight" in geometry && source.strokeWeight !== undefined) geometry.strokeWeight = source.strokeWeight;
      if ("strokeAlign" in geometry && source.strokeAlign) geometry.strokeAlign = source.strokeAlign;
      if ("strokeCap" in geometry && source.strokeCap) geometry.strokeCap = source.strokeCap === "BUTT" ? "NONE" : source.strokeCap;
      if ("strokeJoin" in geometry && source.strokeJoin) geometry.strokeJoin = source.strokeJoin;
      if ("dashPattern" in geometry && source.strokeDashes) geometry.dashPattern = source.strokeDashes;
    }
    if ("cornerRadius" in node && source.cornerRadius !== undefined) node.cornerRadius = source.cornerRadius;
    if (node.type === "TEXT") {
      // Set the base fill before applying ranges; assigning it afterward would erase their colours.
      const overrides: number[] = source.characterStyleOverrides || [];
      for (let start = 0; start < Math.min(overrides.length, node.characters.length);) {
        let end = start + 1;
        while (end < overrides.length && overrides[end] === overrides[start]) end++;
        end = Math.min(end, node.characters.length);
        const range = (source.styleOverrideTable || {})[String(overrides[start])];
        if (range?.fills) node.setRangeFills(start, end, paints(range.fills));
        start = end;
      }
      node.textAutoResize = source.style?.textAutoResize || "NONE";
    }
    if (node.type === "FRAME") {
      node.clipsContent = source.clipsContent ?? false;
      for (const child of source.children || []) await emit(child, node);
      if (source.layoutMode) {
        node.layoutMode = source.layoutMode;
        for (const key of ["itemSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
          "primaryAxisSizingMode", "counterAxisSizingMode", "primaryAxisAlignItems", "counterAxisAlignItems"] as const) {
          if (source[key] !== undefined) (node as any)[key] = source[key];
        }
      }
      if (source.type === "GROUP" && node.children.length) {
        const frame = node;
        const group = figma.group([...frame.children], parent);
        groupOrigin = [[1, 0, group.x], [0, 1, group.y]];
        frame.remove();
        node = group;
        node.name = source.name;
      }
    }
    node.relativeTransform = matrixMultiply(source.relativeTransform, groupOrigin);
    node.visible = source.visible ?? true;
    node.opacity = source.opacity ?? 1;
    node.blendMode = source.blendMode || "NORMAL";
    if (source.effects) node.effects = source.effects;
    if (source.isMask) node.isMask = true;
    return node;
  }
  const created: PageNode[] = [];
  const original = figma.currentPage;
  try {
    for (const source of data.document.children) {
      const page = figma.createPage();
      created.push(page);
      page.name = source.name;
      await figma.setCurrentPageAsync(page);
      for (const child of source.children || []) await emit(child, page);
      report.pages++;
    }
    await figma.setCurrentPageAsync(created[0]);
    figma.viewport.scrollAndZoomIntoView([...created[0].children]);
  } catch (error) {
    await figma.setCurrentPageAsync(original);
    for (const page of created) page.remove();
    throw error;
  }
  for (const item of data.report?.unmapped || []) report.warnings.push(`${item.layer || item.page || "Document"}: ${item.reason}`);
  return report;
}

let importing = false;
figma.ui.onmessage = async (message: RecordData) => {
  if (message.type !== "import" || importing) return;
  importing = true;
  try {
    const report = await importDocument(message.data);
    figma.ui.postMessage({ type: "done", report });
  } catch (error) {
    figma.ui.postMessage({ type: "error", message: error instanceof Error ? error.message : String(error) });
  } finally {
    importing = false;
  }
};
