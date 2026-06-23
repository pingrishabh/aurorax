import { toast } from "sonner";
import { Sidebar } from "@/components/Sidebar";
import { ChatPane } from "@/components/ChatPane";
import { useChat } from "@/hooks/useChat";

export default function App() {
  const chat = useChat();
  const activeTitle =
    chat.sessions.find((s) => s.id === chat.activeId)?.title ?? "New chat";

  const onSend = async (text: string) => {
    try {
      await chat.sendMessage(text);
    } catch (e) {
      toast.error("Failed to send message");
      console.error(e);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar
        sessions={chat.sessions}
        activeId={chat.activeId}
        onSelect={chat.setActiveId}
        onNew={chat.newSession}
        onRename={chat.renameSession}
        onDelete={chat.deleteSession}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center border-b border-border px-5">
          <span className="min-w-0 truncate text-sm font-medium text-foreground">
            {activeTitle}
          </span>
        </header>
        <ChatPane
          messages={chat.messages}
          streaming={chat.isStreaming}
          onSend={onSend}
          onStop={chat.cancelActive}
        />
      </div>
    </div>
  );
}
