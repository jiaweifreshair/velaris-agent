/**
 * 记忆存储层
 * 基于文件系统的记忆持久化
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import type {
  MemoryEntry,
  MemoryConfig,
  MemoryIndexEntry,
  MemoryLoadResult,
  MemoryLayer,
} from './types.js';
import { DEFAULT_MEMORY_CONFIG, parseMemoryType } from './types.js';

/** MEMORY.md 入口文件名 */
export const ENTRYPOINT_NAME = 'MEMORY.md';

/**
 * 记忆存储管理器
 * 负责记忆的文件系统读写、索引管理
 */
export class MemoryStorage {
  private readonly config: MemoryConfig;

  constructor(config: Partial<MemoryConfig> = {}) {
    this.config = { ...DEFAULT_MEMORY_CONFIG, ...config };
  }

  /** 确保记忆目录存在 */
  async ensureDir(): Promise<void> {
    await fs.mkdir(this.config.memoryDir, { recursive: true });
    if (this.config.enableTeamMemory && this.config.teamMemoryDir) {
      await fs.mkdir(this.config.teamMemoryDir, { recursive: true });
    }
  }

  /** 读取 MEMORY.md 索引 */
  async readIndex(): Promise<string> {
    const indexPath = path.join(this.config.memoryDir, ENTRYPOINT_NAME);
    try {
      return await fs.readFile(indexPath, 'utf-8');
    } catch {
      return '';
    }
  }

  /** 写入 MEMORY.md 索引 */
  async writeIndex(entries: MemoryIndexEntry[]): Promise<void> {
    await this.ensureDir();
    const indexPath = path.join(this.config.memoryDir, ENTRYPOINT_NAME);

    // 生成索引内容
    const lines = entries.map((e) => `- [${e.title}](${e.file}) — ${e.hook}`);
    let content = lines.join('\n');

    // 截断检查
    const lineCount = lines.length;

    let wasTruncated = false;
    let truncationReason = '';

    if (lineCount > this.config.maxIndexLines) {
      lines.splice(this.config.maxIndexLines);
      wasTruncated = true;
      truncationReason = `${lineCount} lines (limit: ${this.config.maxIndexLines})`;
    }

    content = lines.join('\n');
    if (Buffer.byteLength(content, 'utf-8') > this.config.maxIndexBytes) {
      // 按字节截断，在最后一个换行处
      const bytes = Buffer.from(content, 'utf-8');
      const cutAt = bytes.lastIndexOf('\n', this.config.maxIndexBytes);
      content = bytes.slice(0, cutAt > 0 ? cutAt : this.config.maxIndexBytes).toString('utf-8');
      wasTruncated = true;
      truncationReason = truncationReason || `exceeds ${this.config.maxIndexBytes} bytes`;
    }

    if (wasTruncated) {
      content += `\n\n> WARNING: ${ENTRYPOINT_NAME} was truncated (${truncationReason}). Keep index entries concise.`;
    }

    await fs.writeFile(indexPath, content, 'utf-8');
  }

  /** 解析 MEMORY.md 索引 */
  async parseIndex(): Promise<MemoryIndexEntry[]> {
    const content = await this.readIndex();
    if (!content.trim()) return [];

    const entries: MemoryIndexEntry[] = [];
    const lines = content.split('\n');

    for (const line of lines) {
      // 解析格式: - [Title](file.md) — hook
      const match = line.match(/^-\s*\[([^\]]+)\]\(([^)]+)\)\s*[—-]\s*(.+)$/);
      if (match) {
        const title = match[1] ?? '';
        const file = match[2] ?? '';
        const hook = match[3] ?? '';
        // 从文件名推断类型
        const typeGuess = file.split('_')[0]?.toLowerCase();
        const type = parseMemoryType(typeGuess) ?? 'project';

        entries.push({ title, file, hook, type });
      }
    }

    return entries;
  }

  /** 读取单个记忆文件 */
  async readMemoryFile(filePath: string): Promise<MemoryEntry | null> {
    try {
      const fullPath = path.join(this.config.memoryDir, filePath);
      const content = await fs.readFile(fullPath, 'utf-8');
      return this.parseMemoryFile(content, filePath);
    } catch {
      return null;
    }
  }

  /** 解析记忆文件（frontmatter + content） */
  parseMemoryFile(content: string, filePath: string): MemoryEntry {
    const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    const now = Date.now();

    if (!frontmatterMatch) {
      // 无 frontmatter，作为纯内容处理
      return {
        id: path.basename(filePath, '.md'),
        name: path.basename(filePath, '.md'),
        description: content.slice(0, 100),
        type: 'project',
        scope: 'private',
        content: content.trim(),
        layer: 'auto',
        createdAt: now,
        updatedAt: now,
        filePath,
      };
    }

    const [, frontmatter, body] = frontmatterMatch;
    const meta: Record<string, string> = {};

    // 解析 frontmatter
    if (frontmatter) {
      for (const line of frontmatter.split('\n')) {
        const [key, ...values] = line.split(':');
        if (key && values.length > 0) {
          meta[key.trim()] = values.join(':').trim();
        }
      }
    }

    return {
      id: path.basename(filePath, '.md'),
      name: meta['name'] ?? path.basename(filePath, '.md'),
      description: meta['description'] ?? '',
      type: parseMemoryType(meta['type']) ?? 'project',
      scope: (meta['scope'] as MemoryEntry['scope']) ?? 'private',
      content: (body ?? '').trim(),
      layer: 'auto',
      createdAt: meta.createdAt ? parseInt(meta.createdAt, 10) : now,
      updatedAt: meta.updatedAt ? parseInt(meta.updatedAt, 10) : now,
      filePath,
      tags: meta.tags?.split(',').map((t) => t.trim()),
    };
  }

  /** 写入记忆文件 */
  async writeMemoryFile(entry: MemoryEntry): Promise<string> {
    await this.ensureDir();

    const fileName = entry.filePath ?? `${entry.type}_${entry.id}.md`;
    const filePath = path.join(this.config.memoryDir, fileName);

    // 生成 frontmatter
    const frontmatter = [
      `name: ${entry.name}`,
      `description: ${entry.description}`,
      `type: ${entry.type}`,
      `scope: ${entry.scope}`,
      `createdAt: ${entry.createdAt}`,
      `updatedAt: ${entry.updatedAt}`,
      ...(entry.tags ? [`tags: ${entry.tags.join(', ')}`] : []),
    ].join('\n');

    const content = `---\n${frontmatter}\n---\n\n${entry.content}`;

    await fs.writeFile(filePath, content, 'utf-8');

    return fileName;
  }

  /** 删除记忆文件 */
  async deleteMemoryFile(filePath: string): Promise<void> {
    const fullPath = path.join(this.config.memoryDir, filePath);
    try {
      await fs.unlink(fullPath);
    } catch {
      // 文件不存在，忽略
    }
  }

  /** 加载所有记忆 */
  async loadAll(): Promise<MemoryLoadResult> {
    await this.ensureDir();

    const entries: MemoryEntry[] = [];
    const byLayer: Record<MemoryLayer, MemoryEntry[]> = {
      company: [],
      project: [],
      user: [],
      auto: [],
      session: [],
      subagent: [],
    };

    // 读取索引
    const indexEntries = await this.parseIndex();
    const indexContent = await this.readIndex();

    // 加载索引中的所有记忆
    for (const idx of indexEntries) {
      const entry = await this.readMemoryFile(idx.file);
      if (entry) {
        entries.push(entry);
        byLayer[entry.layer].push(entry);
      }
    }

    // 检查截断
    const lines = indexContent.split('\n');
    const wasTruncated = lines.length > this.config.maxIndexLines ||
      Buffer.byteLength(indexContent, 'utf-8') > this.config.maxIndexBytes;

    return {
      entries,
      byLayer,
      indexContent,
      wasTruncated,
      truncationReason: wasTruncated ? 'exceeds limits' : undefined,
    };
  }

  /** 搜索记忆 */
  async search(query: string, limit = 10): Promise<MemoryEntry[]> {
    const { entries } = await this.loadAll();
    const lowerQuery = query.toLowerCase();

    // 简单的关键词匹配
    const scored = entries.map((entry) => {
      let score = 0;
      const text = `${entry.name} ${entry.description} ${entry.content}`.toLowerCase();

      // 完全匹配
      if (text.includes(lowerQuery)) {
        score += 10;
      }

      // 名称匹配
      if (entry.name.toLowerCase().includes(lowerQuery)) {
        score += 5;
      }

      // 描述匹配
      if (entry.description.toLowerCase().includes(lowerQuery)) {
        score += 3;
      }

      // 标签匹配
      if (entry.tags?.some((t) => t.toLowerCase().includes(lowerQuery))) {
        score += 2;
      }

      return { entry, score };
    });

    return scored
      .filter((s) => s.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
      .map((s) => s.entry);
  }

  /** 获取配置 */
  getConfig(): MemoryConfig {
    return this.config;
  }
}
