const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

// Browsers' built-in EventSource only supports GET, but our endpoint takes
// a JSON body via POST, so we parse the text/event-stream format by hand
// off a fetch() ReadableStream instead.
export async function streamQuery(question, { onNodeUpdate, onDone, onError, signal } = {}) {
  let response

  try {
    response = await fetch(`${API_BASE}/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    })
  } catch (err) {
    onError?.(err)
    return
  }

  if (!response.ok || !response.body) {
    onError?.(new Error(`Request failed with status ${response.status}`))
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE events are separated by a blank line ("\n\n"); a chunk from
      // the network can contain zero, one, or several complete events.
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        dispatchEvent(rawEvent, { onNodeUpdate, onDone })
        boundary = buffer.indexOf('\n\n')
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      onError?.(err)
    }
  }
}

function dispatchEvent(rawEvent, { onNodeUpdate, onDone }) {
  let eventType = 'message'
  const dataLines = []

  for (const line of rawEvent.split('\n')) {
    if (line.startsWith('event:')) {
      eventType = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim())
    }
  }

  if (dataLines.length === 0) return

  const data = JSON.parse(dataLines.join('\n'))

  if (eventType === 'node_update') {
    onNodeUpdate?.(data)
  } else if (eventType === 'done') {
    onDone?.(data)
  }
}
