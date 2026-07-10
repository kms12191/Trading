export function shouldSubmitChatbotInput(event) {
  const isComposing = Boolean(
    event?.nativeEvent?.isComposing
    || event?.isComposing
    || event?.keyCode === 229
  )
  return event?.key === 'Enter' && !event?.shiftKey && !isComposing
}
