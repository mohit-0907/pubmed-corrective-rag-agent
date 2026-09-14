// Anchor ids are scoped by message: the same source number appears in every
// answer on the page, so an id of just the number would collide and a
// citation marker would scroll to the wrong message's source list.
//
// Lives here rather than beside CitationList so that component's module only
// exports a component, which is what React Fast Refresh needs.
export function sourceAnchorId(messageId, number) {
  return `source-${messageId}-${number}`
}
