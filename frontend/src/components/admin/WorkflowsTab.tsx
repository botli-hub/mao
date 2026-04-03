import React, { useEffect, useState } from 'react'
import { Plus, Trash2, Upload, RotateCcw } from 'lucide-react'
import { workflowAPI } from '../../api/services'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import type { Workflow } from '../../types'
import toast from 'react-hot-toast'

type WorkflowSnapshot = {
  snapshot_id: string
  version: string
  published_at: string
  published_by: string
}

export function WorkflowsTab() {
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [newName, setNewName] = useState('')
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Workflow | null>(null)
  const [snapshots, setSnapshots] = useState<WorkflowSnapshot[]>([])

  useEffect(() => {
    void loadWorkflows()
  }, [])

  useEffect(() => {
    if (!selectedWorkflowId) {
      setDetail(null)
      setSnapshots([])
      return
    }
    void loadDetail(selectedWorkflowId)
  }, [selectedWorkflowId])

  const loadWorkflows = async () => {
    setIsLoading(true)
    try {
      const res = await workflowAPI.list()
      setWorkflows(res.data.items)
      if (res.data.items[0] && !selectedWorkflowId) {
        setSelectedWorkflowId(res.data.items[0].workflow_id)
      }
    } catch (err) {
      toast.error('加载工作流失败')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const loadDetail = async (workflowId: string) => {
    try {
      const [detailRes, snapshotsRes] = await Promise.all([
        workflowAPI.get(workflowId),
        workflowAPI.getSnapshots(workflowId),
      ])
      setDetail(detailRes.data)
      setSnapshots(snapshotsRes.data)
    } catch (err) {
      toast.error('加载工作流详情失败')
      console.error(err)
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const res = await workflowAPI.create(newName.trim())
      setWorkflows((prev) => [res.data, ...prev])
      setSelectedWorkflowId(res.data.workflow_id)
      setNewName('')
      toast.success('创建工作流成功')
    } catch (err) {
      toast.error('创建工作流失败')
      console.error(err)
    }
  }

  const handleDelete = async (workflowId: string) => {
    if (!confirm('确认删除该工作流？')) return
    try {
      await workflowAPI.delete(workflowId)
      const next = workflows.filter((item) => item.workflow_id !== workflowId)
      setWorkflows(next)
      setSelectedWorkflowId(next[0]?.workflow_id ?? null)
      toast.success('删除工作流成功')
    } catch (err) {
      toast.error('删除工作流失败')
      console.error(err)
    }
  }

  const handlePublish = async () => {
    if (!selectedWorkflowId) return
    try {
      await workflowAPI.publish(selectedWorkflowId)
      toast.success('发布成功')
      await loadWorkflows()
      await loadDetail(selectedWorkflowId)
    } catch (err) {
      toast.error('发布失败')
      console.error(err)
    }
  }

  const handleRollback = async (version: string) => {
    if (!selectedWorkflowId) return
    try {
      await workflowAPI.rollback(selectedWorkflowId, version)
      toast.success(`已回滚至 ${version}`)
      await loadWorkflows()
      await loadDetail(selectedWorkflowId)
    } catch (err) {
      toast.error('回滚失败')
      console.error(err)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex gap-3 items-end">
        <Input label="新建工作流" value={newName} onChange={(e) => setNewName(e.target.value)} />
        <Button onClick={handleCreate}>
          <Plus className="w-4 h-4 mr-1" />创建
        </Button>
      </div>

      {isLoading ? (
        <div className="text-gray-500">加载中...</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card title="工作流列表">
            <div className="space-y-2">
              {workflows.map((workflow) => (
                <div
                  key={workflow.workflow_id}
                  className={`p-3 rounded-lg border cursor-pointer ${
                    selectedWorkflowId === workflow.workflow_id
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                  onClick={() => setSelectedWorkflowId(workflow.workflow_id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-gray-900">{workflow.name}</p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        节点 {workflow.dag_definition.nodes.length} · 边 {workflow.dag_definition.edges.length}
                      </p>
                    </div>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => void handleDelete(workflow.workflow_id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
              {workflows.length === 0 && <p className="text-sm text-gray-500">暂无工作流</p>}
            </div>
          </Card>

          <Card title="工作流详情">
            {!detail ? (
              <p className="text-sm text-gray-500">请选择工作流</p>
            ) : (
              <div className="space-y-4">
                <div className="text-sm text-gray-700 space-y-1">
                  <p>名称：{detail.name}</p>
                  <p>描述：{detail.description || '-'}</p>
                  <p>状态：{detail.is_active ? '启用' : '禁用'}</p>
                  <p>节点数：{detail.dag_definition.nodes.length}</p>
                  <p>边数：{detail.dag_definition.edges.length}</p>
                </div>
                <Button onClick={() => void handlePublish()}>
                  <Upload className="w-4 h-4 mr-1" />发布当前版本
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
