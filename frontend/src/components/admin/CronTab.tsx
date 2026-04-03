import React, { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { cronAPI } from '../../api/services'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import type { CronJob } from '../../types'
import toast from 'react-hot-toast'

export function CronTab() {
  const [jobs, setJobs] = useState<CronJob[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    void loadJobs()
  }, [])

  const loadJobs = async () => {
    setIsLoading(true)
    try {
      const res = await cronAPI.list()
      setJobs(res.data.items)
    } catch (err) {
      toast.error('加载 Cron 任务失败')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleToggle = async (job: CronJob) => {
    try {
      await cronAPI.toggle(job.cron_id, !job.is_active)
      setJobs((prev) =>
        prev.map((item) =>
          item.cron_id === job.cron_id ? { ...item, is_active: !item.is_active } : item,
        ),
      )
    } catch (err) {
      toast.error('切换状态失败')
      console.error(err)
    }
  }

  const handleDelete = async (cronId: string) => {
    if (!confirm('确认删除该 Cron 任务？')) return
    try {
      await cronAPI.delete(cronId)
      setJobs((prev) => prev.filter((item) => item.cron_id !== cronId))
      toast.success('删除 Cron 任务成功')
    } catch (err) {
      toast.error('删除 Cron 任务失败')
      console.error(err)
    }
  }

  if (isLoading) {
    return <div className="text-gray-500">加载中...</div>
  }

  if (jobs.length === 0) {
    return <Card className="text-center text-gray-500 py-10">暂无 Cron 任务</Card>
  }

  return (
    <div className="space-y-4">
      {jobs.map((job) => (
        <Card key={job.cron_id} title={job.name} description={job.cron_expr}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-gray-600 mb-4">
            <p>时区：{job.timezone}</p>
            <p>策略：{job.overlap_policy}</p>
            <p>上次执行：{job.last_run_at ? new Date(job.last_run_at).toLocaleString() : '-'}</p>
            <p>下次执行：{job.next_run_at ? new Date(job.next_run_at).toLocaleString() : '-'}</p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => void handleToggle(job)}>
              {job.is_active ? '暂停' : '恢复'}
            </Button>
            <Button variant="danger" size="sm" onClick={() => void handleDelete(job.cron_id)}>
              <Trash2 className="w-4 h-4 mr-1" />删除
            </Button>
          </div>
        </Card>
      ))}
    </div>
  )
}
