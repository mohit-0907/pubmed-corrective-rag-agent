// The generation LLM sometimes emphasizes a study/paper name with markdown
// bold (**like this**) even though the system prompt never asks for
// markdown. Rendered as plain text, that shows up as literal asterisks -
// this splits on **bold** spans and renders them as <strong> instead.
export function renderInlineMarkdown(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)

  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={index} className="font-semibold text-stone-900">
          {part.slice(2, -2)}
        </strong>
      )
    }
    return part
  })
}
