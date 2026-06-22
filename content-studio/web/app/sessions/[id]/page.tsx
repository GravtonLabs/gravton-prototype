'use client'
import { useParams } from 'next/navigation'
import ChatArea from '@/components/ChatArea'

export default function SessionPage() {
  const { id } = useParams<{ id: string }>()
  return <ChatArea sessionId={id} />
}
