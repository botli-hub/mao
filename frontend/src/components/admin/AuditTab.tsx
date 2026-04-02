import React, { useEffect, useState } from 'react'
import { auditAPI } from '../../api/services'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import type { TraceDetail } from '../../types'
import toast from 'react-hot-toast'

export function AuditTab() {
  const [traces, setTraces] = useState<TraceDetail[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    loadTraces()
  }, [])

  const loadTraces = async () => {
    setIsLoading(true)
    try {
      const res = await auditAPI.getTraces()
      setTraces(res.data.items)
    } catch (err) {
      toast.error('加载审计日志失败')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-900">执行审计</h2>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : traces.length === 0 ? (
        <Card className="text-center py-12 text-gray-500">暂无审计记录</Card>
      ) : (
        <div className="space-y-4">
          {traces.map((trace) => (
            <Card key={trace.trace_id} title={`Trace ${trace.trace_id}`}>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">状态：</span>
                    {trace.status}
                  </p>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">步骤数：</span>
                    {trace.step_count}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">总 Token：</span>
                    {trace.total_tokens.total}
                  </p>
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">时间：</span>
                    {new Date(trace.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
              <Button size="sm" onClick={() => console.log('View trace:', trace.trace_id)}>
                查看详情
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
