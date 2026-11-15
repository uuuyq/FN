import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownReply({ content }: { content: string }) {
  return (
    <div className="markdown-reply">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          table: ({ children }) => (
            <div className="markdown-table" tabIndex={0} aria-label="回复表格">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
