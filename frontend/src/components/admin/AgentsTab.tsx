import React, { useEffect, useState } from 'react'
import { Plus, Trash2, Upload, RotateCcw } from 'lucide-react'
import { agentAPI } from '../../api/services'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import type { Agent, AgentDetail, AgentSnapshot } from '../../types'
import toast from 'react-hot-toast'

export function AgentsTab() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [newName, setNewName] = useState('')
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [detail, setDetail] = useState<AgentDetail | null>(null)
  const [snapshots, setSnapshots] = useState<AgentSnapshot[]>([])

  useEffect(() => {
    void loadAgents()
  }, [])

  useEffect(() => {
    if (!selectedAgentId) {
      setDetail(null)
      setSnapshots([])
      return
    }
    void loadDetail(selectedAgentId)
  }, [selectedAgentId])

  const loadAgents = async () => {
    setIsLoading(true)
    try {
      const res = await agentAPI.list()
      setAgents(res.data.items)
      if (res.data.items[0] && !selectedAgentId) {
        setSelectedAgentId(res.data.items[0].agent_id)
      }
    } catch (err) {
      toast.error('加载 Agent 失败')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const loadDetail = async (agentId: string) => {
    try {
      const [detailRes, snapshotsRes] = await Promise.all([
        agentAPI.get(agentId),
        agentAPI.getSnapshots(agentId),
      ])
      setDetail(detailRes.data)
      setSnapshots(snapshotsRes.data)
    } catch (err) {
      toast.error('加载 Agent 详情失败')
      console.error(err)
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const res = await agentAPI.create(newName.trim())
      setAgents((prev) => [res.data, ...prev])
      setSelectedAgentId(res.data.agent_id)
      setNewName('')
      toast.success('创建 Agent 成功')
    } catch (err) {
      toast.error('创建 Agent 失败')
      console.error(err)
    }
  }

  const handleDelete = async (agentId: string) => {
    if (!confirm('确认删除该 Agent？')) return
    try {
      await agentAPI.delete(agentId)
      const next = agents.filter((item) => item.agent_id !== agentId)
      setAgents(next)
      setSelectedAgentId(next[0]?.agent_id ?? null)
      toast.success('删除 Agent 成功')
    } catch (err) {
      toast.error('删除 Agent 失败')
      console.error(err)
    }
  }

  const handlePublish = async () => {
    if (!selectedAgentId) return
    try {
      await agentAPI.publish(selectedAgentId)
      toast.success('发布成功')
      await loadAgents()
      await loadDetail(selectedAgentId)
    } catch (err) {
      toast.error('发布失败')
      console.error(err)
    }
  }

  const handleRollback = async (version: string) => {
    if (!selectedAgentId) return
    try {
      await agentAPI.rollback(selectedAgentId, version)
      toast.success(`已回滚至 ${version}`)
      await loadAgents()
      await loadDetail(selectedAgentId)
    } catch (err) {
      toast.error('回滚失败')
      console.error(err)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex gap-3 items-end">
        <Input label="新建 Agent" value={newName} onChange={(e) => setNewName(e.target.value)} />
        <Button onClick={handleCreate}>
          <Plus className="w-4 h-4 mr-1" />创建
        </Button>
      </div>

      {isLoading ? (
        <div className="text-gray-500">加载中...</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card title="Agent 列表">
            <div className="space-y-2">
              {agents.map((agent) => (
                <div
                  key={agent.agent_id}
                  className={`p-3 rounded-lg border cursor-pointer ${
                    selectedAgentId === agent.agent_id
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                  onClick={() => setSelectedAgentId(agent.agent_id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-gray-900">{agent.name}</p>
                      <p className="text-xs text-gray-500 mt-0.5">版本：{agent.current_version ?? '未发布'}</p>
                    </div>
                    <Button variant="danger" size="sm" onClick={() => void handleDelete(agent.agent_id)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
              {agents.length === 0 && <p className="text-sm text-gray-500">暂无 Agent</p>}
            </div>
          </Card>

          <Card title="Agent 详情">
            {!detail ? (
              <p className="text-sm text-gray-500">请选择 Agent</p>
            ) : (
              <div className="space-y-4">
                <div className="text-sm text-gray-700 space-y-1">
                  <p>名称：{detail.name}</p>
                  <p>描述：{detail.description || '-'}</p>
                  <p>当前版本：{detail.current_version ?? '未发布'}</p>
                  <p>挂载技能数：{detail.skill_ids.length}</p>
                  <p>模型：{detail.model_config.provider}/{detail.model_config.model}</p>
                </div>
                <Button onClick={() => void handlePublish()}>
                  <Upload className="w-4 h-4 mr-1" />发布当前草稿
                </Button>

                <div>
                  <h4 className="text-sm font-semibold text-gray-800 mb-2">历史快照</h4>
                  <div className="space-y-2 max-h-44 overflow-y-auto">
                    {snapshots.map((snapshot) => (
                      <div
                        key={snapshot.snapshot_id}
                        className="flex items-center justify-between border border-gray-200 rounded p-2"
                      >
                        <div>
                          <p className="text-sm font-medium">{snapshot.version}</p>
                          <p className="text-xs text-gray-500">
                            {new Date(snapshot.published_at).toLocaleString()}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="default"
                          onClick={() => void handleRollback(snapshot.version)}
                        >
                          <RotateCcw className="w-3.5 h-3.5 mr-1" />回滚
                        </Button>
                      </div>
                    ))}
                    {snapshots.length === 0 && <p className="text-xs text-gray-500">暂无快照</p>}
                  </div>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
