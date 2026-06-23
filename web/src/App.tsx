import { toast } from "sonner";
import { Sidebar } from "@/components/Sidebar";
import { ChatPane } from "@/components/ChatPane";
import { useChat } from "@/hooks/useChat";

export default function App() {
  const chat = useChat();

  const onSend = async (text: string) => {
    try {
      await chat.sendMessage(text);
    } catch (e) {
      toast.error("Failed to send message");
      console.error(e);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        sessions={chat.sessions}
        activeId={chat.activeId}
        onSelect={chat.setActiveId}
        onNew={chat.newSession}
        onRename={chat.renameSession}
        onDelete={chat.deleteSession}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center border-b border-border px-4">
          <span className="text-sm font-medium tracking-tight">Mock Chat</span>
          <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            steerable · horizontally scalable
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
