import type { Meta, StoryObj } from '@storybook/web-components'
import { Button } from './Button'
import type { ButtonProps } from './types'

const meta: Meta<ButtonProps> = {
  title: 'Components/Button',
  component: 'e-button',
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'success', 'danger', 'warning', 'info', 'ghost', 'text'],
      description: '按钮变体',
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
      description: '按钮尺寸',
    },
    disabled: {
      control: 'boolean',
      description: '是否禁用',
    },
    loading: {
      control: 'boolean',
      description: '是否加载中',
    },
    block: {
      control: 'boolean',
      description: '是否块级按钮',
    },
    text: {
      control: 'text',
      description: '按钮文字',
    },
  },
}

export default meta
type Story = StoryObj<ButtonProps>

/**
 * 主按钮 — 用于主要操作
 */
export const Primary: Story = {
  args: {
    text: '主按钮',
    variant: 'primary',
  },
  render: (args) => Button(args),
}

/**
 * 次要按钮 — 用于次要操作
 */
export const Secondary: Story = {
  args: {
    text: '次要按钮',
    variant: 'secondary',
  },
  render: (args) => Button(args),
}

/**
 * 成功按钮
 */
export const Success: Story = {
  args: {
    text: '成功',
    variant: 'success',
  },
  render: (args) => Button(args),
}

/**
 * 危险按钮
 */
export const Danger: Story = {
  args: {
    text: '删除',
    variant: 'danger',
  },
  render: (args) => Button(args),
}

/**
 * 幽灵按钮
 */
export const Ghost: Story = {
  args: {
    text: '幽灵按钮',
    variant: 'ghost',
  },
  render: (args) => Button(args),
}

/**
 * 文字按钮
 */
export const Text: Story = {
  args: {
    text: '文字按钮',
    variant: 'text',
  },
  render: (args) => Button(args),
}

/**
 * 小按钮
 */
export const Small: Story = {
  args: {
    text: '小按钮',
    size: 'sm',
  },
  render: (args) => Button(args),
}

/**
 * 大按钮
 */
export const Large: Story = {
  args: {
    text: '大按钮',
    size: 'lg',
  },
  render: (args) => Button(args),
}

/**
 * 加载中
 */
export const Loading: Story = {
  args: {
    text: '加载中',
    loading: true,
  },
  render: (args) => Button(args),
}

/**
 * 禁用状态
 */
export const Disabled: Story = {
  args: {
    text: '禁用',
    disabled: true,
  },
  render: (args) => Button(args),
}

/**
 * 块级按钮
 */
export const Block: Story = {
  args: {
    text: '块级按钮',
    block: true,
  },
  render: (args) => Button(args),
}

/**
 * 所有变体
 */
export const AllVariants: Story = {
  render: () => `
    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
      ${Button({ text: 'Primary', variant: 'primary' })}
      ${Button({ text: 'Secondary', variant: 'secondary' })}
      ${Button({ text: 'Success', variant: 'success' })}
      ${Button({ text: 'Danger', variant: 'danger' })}
      ${Button({ text: 'Warning', variant: 'warning' })}
      ${Button({ text: 'Info', variant: 'info' })}
      ${Button({ text: 'Ghost', variant: 'ghost' })}
      ${Button({ text: 'Text', variant: 'text' })}
    </div>
  `,
}

/**
 * 所有尺寸
 */
export const AllSizes: Story = {
  render: () => `
    <div style="display: flex; gap: 8px; align-items: center;">
      ${Button({ text: 'Small', size: 'sm' })}
      ${Button({ text: 'Medium', size: 'md' })}
      ${Button({ text: 'Large', size: 'lg' })}
    </div>
  `,
}
