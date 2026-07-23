import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const markdownComponents = {
  a: ({ ...props }) => (
    <a 
      target="_blank" 
      rel="noopener noreferrer" 
      className="text-cyan-400 hover:underline break-all" 
      {...props} 
    />
  ),
  table: ({ ...props }) => (
    <div className="my-2 overflow-x-auto rounded border border-slate-700/80">
      <table className="w-full min-w-full border-collapse text-left text-[11px]" {...props} />
    </div>
  ),
  thead: ({ ...props }) => (
    <thead className="bg-slate-900/80 text-[10px] uppercase tracking-[0.08em] text-slate-400" {...props} />
  ),
  tbody: ({ ...props }) => (
    <tbody className="divide-y divide-slate-800/80 bg-slate-950/20" {...props} />
  ),
  tr: ({ ...props }) => <tr className="hover:bg-slate-800/20" {...props} />,
  th: ({ ...props }) => (
    <th className="whitespace-nowrap px-2.5 py-2 font-bold border-r border-slate-800/80 last:border-r-0" {...props} />
  ),
  td: ({ ...props }) => (
    <td className="whitespace-normal px-2.5 py-2 text-slate-200 border-r border-slate-800/80 last:border-r-0" {...props} />
  ),
  p: ({ ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props} />,
  ul: ({ ...props }) => <ul className="my-2 ml-4 list-disc space-y-1" {...props} />,
  ol: ({ ...props }) => <ol className="my-2 ml-4 list-decimal space-y-1" {...props} />,
  li: ({ ...props }) => <li className="text-[11px] text-slate-300" {...props} />,
  strong: ({ ...props }) => <strong className="font-bold text-slate-50" {...props} />,
  em: ({ ...props }) => <em className="italic text-slate-300" {...props} />,
}


export default function ChatMarkdown({ messageText }) {
  if (!messageText) return null

  return (
    <div className="markdown-content whitespace-pre-wrap break-words text-xs leading-5 text-slate-100">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
      >
        {messageText}
      </ReactMarkdown>
    </div>
  )
}
