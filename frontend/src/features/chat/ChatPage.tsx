import { useParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { useUiStore } from '@/store/ui'
import { ConversationSidebar } from './ConversationSidebar'
import { ConversationView } from './ConversationView'

export function ChatPage() {
  const { conversationId } = useParams()
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)
  return (
    <div className="chat">
      <ConversationSidebar />
      {conversationId ? (
        <ConversationView key={conversationId} conversationId={conversationId} />
      ) : (
        <div className="chat-main">
          <header className="chat-header">
            {!sidebarOpen && (
              <button className="btn btn-ghost btn-sm" onClick={toggleSidebar} aria-label="Show sidebar">
                »
              </button>
            )}
            <span className="title">Chat</span>
          </header>
          <div className="chat-scroll">
            <EmptyState title="Pick a conversation or start a new one">Use the “+ New” button in the sidebar, or press Cmd/Ctrl+K to search.</EmptyState>
          </div>
        </div>
      )}
    </div>
  )
}
