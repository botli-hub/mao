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

import type { CardSchema } from '../../types'
import { Button } from './Button'

interface GUICardProps {
  schema: CardSchema
  onActionClick: (actionId: string, formData?: Record<string, unknown>) => void
  isLoading?: boolean
  isLocked?: boolean
}

export function GUICard({ schema, onActionClick, isLoading, isLocked }: GUICardProps) {
  const [formData, setFormData] = React.useState<Record<string, unknown>>({})
  const selectIntentActions = schema.actions.filter((item) => item.action_type === 'SELECT_INTENT')

  const handleActionClick = (actionId: string) => {
    const action = schema.actions.find((a) => a.action_id === actionId)
    if (action?.action_type === 'SUBMIT_FORM') {
      onActionClick(actionId, formData)
      return
    }

    if (action?.action_type === 'SELECT_INTENT') {
      onActionClick(actionId, { ...formData, selected_intent: actionId })
      return
    }

    onActionClick(actionId)
  }

  return (
    <Card title={schema.title} description={schema.description} className={isLocked ? 'opacity-70' : ''}>
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
                  disabled={isLocked || isLoading}
                  value={String(formData[field.key] ?? '')}
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
                  disabled={isLocked || isLoading}
                  type={field.type}
                  placeholder={field.placeholder}
                  value={String(formData[field.key] ?? '')}
                  onChange={(e) => setFormData({ ...formData, [field.key]: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}
            </div>
          ))}
        </div>
      )}

      {selectIntentActions.length > 0 && (
        <div className="mb-5 space-y-2">
          <p className="text-sm font-medium text-gray-700">请选择意图承接方</p>
          {selectIntentActions.map((action) => (
            <button
              key={action.action_id}
              type="button"
              disabled={Boolean(isLocked) || Boolean(isLoading)}
              onClick={() => handleActionClick(action.action_id)}
              className="w-full text-left text-sm px-3 py-2 rounded-md border border-gray-200 hover:bg-gray-50 disabled:opacity-60"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-3 flex-wrap">
        {schema.actions
          .filter((action) => action.action_type !== 'SELECT_INTENT')
          .map((action) => (
            <Button
              key={action.action_id}
              variant={
                action.style === 'danger'
                  ? 'danger'
                  : action.style === 'primary'
                    ? 'primary'
                    : 'default'
              }
              onClick={() => handleActionClick(action.action_id)}
              isLoading={isLoading}
              disabled={Boolean(isLocked) || (schema.client_side_lock && isLoading)}
            >
              {action.label}
            </Button>
          ))}
      </div>
    </Card>
  )
}
