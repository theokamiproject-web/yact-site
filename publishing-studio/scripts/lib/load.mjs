// Load an issue directory into an in-memory Publication Model. Never throws on content problems:
// problems are collected in model.loadErrors so `validate` can report them all at once.
import fs from 'node:fs';
import path from 'node:path';
import * as yaml from 'js-yaml';
import { issueDir } from './paths.mjs';
import { parseBlocks } from './text.mjs';

export const IMAGE_EXT = /\.(jpe?g|png|webp|tif?f|gif|svg)$/i;

function readYaml(file, errors, { required = true } = {}) {
  if (!fs.existsSync(file)) {
    if (required) errors.push({ code: 'FILE_MISSING', file: path.basename(file), message: `${path.basename(file)} not found` });
    return undefined;
  }
  try {
    return yaml.load(fs.readFileSync(file, 'utf8')) ?? {};
  } catch (e) {
    errors.push({ code: 'YAML_PARSE', file: path.basename(file), message: e.message.split('\n')[0] });
    return undefined;
  }
}

export function parseFrontMatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return { meta: undefined, body: text };
  return { meta: yaml.load(m[1]) ?? {}, body: m[2] };
}

export function loadIssue(id) {
  const dir = issueDir(id);
  const loadErrors = [];
  const model = { id, dir, loadErrors };
  if (!fs.existsSync(dir)) {
    loadErrors.push({ code: 'ISSUE_MISSING', file: id, message: `issue directory not found: ${dir}` });
    model.articles = {};
    model.images = {};
    model.captions = {};
    model.imageMeta = {};
    return model;
  }
  model.issue = readYaml(path.join(dir, 'issue.yaml'), loadErrors);
  model.editorial = readYaml(path.join(dir, 'editorial.yaml'), loadErrors);
  model.flatplan = readYaml(path.join(dir, 'flatplan.yaml'), loadErrors);
  model.credits = readYaml(path.join(dir, 'credits.yaml'), loadErrors, { required: false }) ?? {};

  // articles/*.md
  model.articles = {};
  model.articleFiles = {};
  const adir = path.join(dir, 'articles');
  if (fs.existsSync(adir)) {
    for (const f of fs.readdirSync(adir).filter((x) => x.endsWith('.md')).sort()) {
      try {
        const { meta, body } = parseFrontMatter(fs.readFileSync(path.join(adir, f), 'utf8'));
        if (!meta) {
          loadErrors.push({ code: 'ARTICLE_NO_FRONTMATTER', file: `articles/${f}`, message: 'front matter (--- yaml ---) missing' });
          continue;
        }
        const key = meta.id ?? f.replace(/\.md$/, '');
        if (model.articles[key]) loadErrors.push({ code: 'ARTICLE_DUPLICATE', file: `articles/${f}`, message: `duplicate article id "${key}"` });
        model.articles[key] = { meta, body, blocks: parseBlocks(body), file: `articles/${f}` };
        model.articleFiles[key] = f;
      } catch (e) {
        loadErrors.push({ code: 'YAML_PARSE', file: `articles/${f}`, message: e.message.split('\n')[0] });
      }
    }
  }

  // captions/*.yaml : {image-file: {caption, credit}}
  model.captions = {};
  const cdir = path.join(dir, 'captions');
  if (fs.existsSync(cdir)) {
    for (const f of fs.readdirSync(cdir).filter((x) => /\.ya?ml$/.test(x)).sort()) {
      const data = readYaml(path.join(cdir, f), loadErrors, { required: false });
      for (const [k, v] of Object.entries(data ?? {})) model.captions[k] = typeof v === 'string' ? { caption: v } : v;
    }
  }

  // images/ + optional images/images.yaml (Photo Editor metadata)
  model.images = {};
  const idir = path.join(dir, 'images');
  if (fs.existsSync(idir)) {
    for (const f of fs.readdirSync(idir)) if (IMAGE_EXT.test(f)) model.images[f] = path.join(idir, f);
  }
  model.imageMeta = readYaml(path.join(idir, 'images.yaml'), loadErrors, { required: false }) ?? {};
  return model;
}
