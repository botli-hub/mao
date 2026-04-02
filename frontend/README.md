# MAO Frontend

React 18 + TypeScript + TailwindCSS 前端实现

## 项目结构

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts         ← Axios 客户端 + 拦截器 + SSE 工厂
│   │   └── services.ts       ← API 服务方法
│   ├── types/index.ts        ← TypeScript 类型定义
│   ├── stores/index.ts       ← Zustand 状态管理
│   ├── hooks/useSSE.ts       ← SSE 流式连接 Hook
│   ├── components/
│   │   ├── ui/               ← 基础 UI 组件
│   │   ├── chat/             ← C 端聊天组件
│   │   └── admin/            ← B 端管理组件
│   ├── pages/                ← 页面组件
│   ├── App.tsx               ← 主应用
│   └── main.tsx              ← 入口点
├── vite.config.ts
├── tailwind.config.js
└── package.json
```

## 快速启动

```bash
pnpm install
cp .env.example .env
pnpm dev
```

## 技术栈

- Vite 6 + React 18 + TypeScript 5.7
- TailwindCSS 3.4 + Zustand 5
- Axios + ReactFlow + react-markdown
