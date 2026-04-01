/**
 * WebSocket client for Iuxis chat.
 * Connects to ws://localhost:8000/ws/chat/{channelId}
 * Handles reconnection and message parsing.
 */

type MessageHandler = (data: ChatWSMessage) => void;

export interface SaveSignal {
  text: string;
  suggested_category: string;
  source: string;
}

export interface ChatWSMessage {
  type: 'thinking' | 'response' | 'error' | 'pong';
  content: string;
  channel_id?: number;
  save_signal?: SaveSignal | null;
}

export class IuxisWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: MessageHandler[] = [];
  private reconnectTimer: NodeJS.Timeout | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  constructor(channelId: number) {
    this.url = `ws://localhost:8000/ws/chat/${channelId}`;
  }

  connect(): void {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const data: ChatWSMessage = JSON.parse(event.data);
          this.handlers.forEach(handler => handler(data));
        } catch (e) {
          console.error('Failed to parse WS message:', e);
        }
      };

      this.ws.onclose = () => {
        this.attemptReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
    } catch (e) {
      console.error('WebSocket connection failed:', e);
      this.attemptReconnect();
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  send(message: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ message }));
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler);
    };
  }

  disconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }

  switchChannel(channelId: number): void {
    this.disconnect();
    this.url = `ws://localhost:8000/ws/chat/${channelId}`;
    this.connect();
  }
}
