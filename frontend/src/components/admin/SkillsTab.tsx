import React, { useEffect, useState } from 'react'
import { Plus, Trash2, Edit } from 'lucide-react'
import { skillAPI } from '../../api/services'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import type { Skill } from '../../types'
import toast from 'react-hot-toast'

export function SkillsTab() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    loadSkills()
  }, [])

  const loadSkills = async () => {
    setIsLoading(true)
    try {
      const res = await skillAPI.list()
      setSkills(res.data.items)
    } catch (err) {
      toast.error('加载技能失败')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async (skillId: string) => {
    if (!confirm('确定删除此技能？')) return
    try {
      await skillAPI.delete(skillId)
      setSkills(skills.filter((s) => s.skill_id !== skillId))
      toast.success('删除成功')
    } catch (err) {
      toast.error('删除失败')
      console.error(err)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold text-gray-900">技能列表</h2>
        <Button>
          <Plus className="w-4 h-4 mr-2" />
          新建技能
        </Button>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : skills.length === 0 ? (
        <Card className="text-center py-12 text-gray-500">暂无技能</Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {skills.map((skill) => (
            <Card key={skill.skill_id} title={skill.name} description={skill.description}>
              <div className="mb-4 space-y-2">
                <p className="text-sm text-gray-600">
                  <span className="font-medium">类型：</span>
                  {skill.skill_type}
                </p>
                <p className="text-sm text-gray-600">
                  <span className="font-medium">状态：</span>
                  {skill.is_active ? '启用' : '禁用'}
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="default" size="sm" className="flex-1">
                  <Edit className="w-4 h-4 mr-1" />
                  编辑
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => handleDelete(skill.skill_id)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
