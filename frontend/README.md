# React + TypeScript + Vite

此模板提供了一个极简的设置，使 React 能够在 Vite 中运行，并包含 HMR（热模块替换）和一些 ESLint 规则。

目前，有两个可用的官方插件：

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) 使用 [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) 使用 [SWC](https://swc.rs/)

## React 编译器 (React Compiler)

此模板未启用 React 编译器，因为它会影响开发和构建的性能。要添加它，请参阅[此文档](https://react.dev/learn/react-compiler/installation)。

## 扩展 ESLint 配置

如果您正在开发生产级别的应用程序，我们建议更新配置以启用感知类型的（type-aware）lint 规则：

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // 其他配置...

      // 移除 tseslint.configs.recommended 并替换为以下内容
      tseslint.configs.recommendedTypeChecked,
      // 或者，使用以下内容以应用更严格的规则
      tseslint.configs.strictTypeChecked,
      // 可选：添加以下内容以应用代码风格规则
      tseslint.configs.stylisticTypeChecked,

      // 其他配置...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // 其他选项...
    },
  },
])
```

您还可以安装 [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) 和 [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) 来获取针对 React 的特有 lint 规则：

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // 其他配置...
      // 启用 React 的 lint 规则
      reactX.configs['recommended-typescript'],
      // 启用 React DOM 的 lint 规则
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // 其他选项...
    },
  },
])
```