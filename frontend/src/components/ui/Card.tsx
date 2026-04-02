import React from 'react'
import { cn } from '../../utils/cn'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string
  description?: string
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, title, description, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn('bg-white border border-gray-200 rounded-lg shadow-sm p-6', className)}
        {...props}
      >
        {title && <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>}
        {description && <p className="text-gray-600 text-sm mb-4">{description}</p>}
        {children}
      </div>
    )
  },
)

Card.displayName = 'Card'

// ─── GUI 卡片渲染器 ────────────────────────────────────────────────────────

import type { CardSchema } from '../../types'
import { Button } from './Button'

interface GUICardProps {
  schema: CardSchema
  onActionClick: (actionId: string, formData?: Record<string, unknown>) => void
  isLoading?: boolean
}

export function GUICard({ schema, onActionClick, isLoading }: GUICardProps) {
  const [formData, setFormData] = React.useState<Record<string, unknown>>({})

  const handleActionClick = (actionId: string) => {
    const action = schema.actions.find((a) => a.action_id === actionId)
    if (action?.action_type === 'SUBMIT_FORM') {
      onActionClick(actionId, formData)
    } else {
      onActionClick(actionId)
    }
  }

  return (
    <Card title={schema.title} description={schema.description}>
      {schema.fields && (
        <div className="space-y-4 mb-6">
          {schema.fields.map((field) => (
            <div key={field.key}>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {field.label}
                {field.required && <span className="text-red-500">*</span>}
              </label>
              {field.type === 'select' ? (
                <select
                  value={formData[field.key] ?? ''}
                  onChange={(e) => setFormData({ ...formData, [field.key]: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">{field.placeholder ?? '选择...'}</option>
                  {field.options?.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={field.type}
                  placeholder={field.placeholder}
                  value={formData[field.key] ?? ''}
                  onChange={(e) => setFormData({ ...formData, [field.key]: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-3">
        {schema.actions.map((action) => (
          <Button
            key={action.action_id}
            variant={action.style === 'danger' ? 'danger' : action.style === 'primary' ? 'primary' : 'default'}
            onClick={() => handleActionClick(action.action_id)}
            isLoading={isLoading}
            disabled={schema.client_side_lock && isLoading}
          >
            {action.label}
          </Button>
        ))}
      </div>
    </Card>
  )
}
