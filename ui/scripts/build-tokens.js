/**
 * 构建设计令牌 CSS 文件
 */

import { writeFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { generateCSSVariables } from '../src/tokens/css-variables'

const __dirname = dirname(fileURLToPath(import.meta.url))
const distDir = resolve(__dirname, '../dist')
const output = resolve(distDir, 'tokens.css')

// 确保目录存在
mkdirSync(distDir, { recursive: true })

// 生成并写入
const css = generateCSSVariables()
writeFileSync(output, css, 'utf-8')

console.log(`✓ Generated: ${output}`)
