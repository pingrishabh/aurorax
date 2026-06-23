import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Logo } from "./Logo";
import { cn } from "@/lib/utils";
import type { Session } from "@/lib/types";

interface Props {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export function Sidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  onRename,
  onDelete,
}: Props) {
  return (
    <aside className="flex h-full w-[17rem] shrink-0 flex-col border-r border-border bg-secondary">
      <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-5">
        <Logo className="h-6 w-6 text-sm" />
        <span className="font-display text-xl leading-none text-foreground">
Mock Chat
        </span>
      </div>

      <div className="px-3 py-3">
        <Button className="w-full justify-start" onClick={onNew}>
          <Plus className="h-4 w-4" />
          New chat
        </Button>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-4">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={cn(
              "group flex items-center gap-1 rounded-md px-3 py-2 text-sm",
              s.id === activeId
                ? "bg-card text-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <button
              className="min-w-0 flex-1 truncate text-left"
              onClick={() => onSelect(s.id)}
              title={s.title}
            >
              {s.title || "New chat"}
            </button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 data-[state=open]:opacity-100"
                  aria-label="Chat options"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => {
                    const title = window.prompt("Rename chat", s.title);
                    if (title && title.trim()) onRename(s.id, title.trim());
                  }}
                >
                  <Pencil className="h-4 w-4" />
                  Rename
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="text-destructive focus:bg-destructive/10"
                  onSelect={() => onDelete(s.id)}
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ))}
      </nav>
    </aside>
  );
}
