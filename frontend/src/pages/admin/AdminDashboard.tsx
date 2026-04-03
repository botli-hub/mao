import React, { useState } from 'react'
import { Settings, Zap, GitBranch, BarChart3, Clock3 } from 'lucide-react'
import { SkillsTab } from '../../components/admin/SkillsTab'
import { AgentsTab } from '../../components/admin/AgentsTab'
import { WorkflowsTab } from '../../components/admin/WorkflowsTab'
import { AuditTab } from '../../components/admin/AuditTab'
import { CronTab } from '../../components/admin/CronTab'

type TabType = 'skills' | 'agents' | 'workflows' | 'cron' | 'audit'

export function AdminDashboard() {
  const [activeTab, setActiveTab] = useState<TabType>('skills')

  const tabs: Array<{ id: TabType; label: string; icon: React.ReactNode }> = [
    { id: 'skills', label: '技能管理', icon: <Zap className="w-5 h-5" /> },
    { id: 'agents', label: 'Agent 工厂', icon: <Settings className="w-5 h-5" /> },
    { id: 'workflows', label: '工作流', icon: <GitBranch className="w-5 h-5" /> },
    { id: 'cron', label: 'Cron 调度', icon: <Clock3 className="w-5 h-5" /> },
    { id: 'audit', label: '监控审计', icon: <BarChart3 className="w-5 h-5" /> },
  ]

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">管理后台</h1>
          <div className="flex gap-2 flex-wrap">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === 'skills' && <SkillsTab />}
        {activeTab === 'agents' && <AgentsTab />}
        {activeTab === 'workflows' && <WorkflowsTab />}
        {activeTab === 'cron' && <CronTab />}
        {activeTab === 'audit' && <AuditTab />}
      </div>
    </div>
  )
}
