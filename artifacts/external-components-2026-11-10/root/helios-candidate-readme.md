# @aionbuilders/helios

> WebSocket server implementation for Bun - Production-ready real-time messaging

[![npm version](https://badge.fury.io/js/@aionbuilders%2Fhelios.svg)](https://www.npmjs.com/package/@aionbuilders/helios)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Bun](https://img.shields.io/badge/Bun-%23000000.svg?style=flat&logo=bun&logoColor=white)](https://bun.sh)

## Why Helios?

**Not Socket.IO, not bare WebSocket** - Helios sits in between:
- More structured than raw WebSocket
- Less opinionated than Socket.IO
- Leverages Bun's native performance
- Built on solid primitives

## Features

### ✨ Production Ready
- 🔐 **Session Recovery** - Reconnect without data loss (JWT-based)
- 💓 **Health Checks** - Automatic ping/pong keep-alive
- 📡 **Room Manager** - Broadcast with permission validators
- 🎯 **RPC Methods** - Request/response with middleware
- 📢 **Pub/Sub Events** - Topic-based subscriptions
- 🧹 **Clean Lifecycle** - Proper connection cleanup

### 🚀 Performance
- Native Bun.serve WebSocket
- Zero-copy message passing
- Efficient pattern matching
- Minimal overhead

### 🛠️ Developer Experience
- TypeScript definitions
- Comprehensive JSDoc
- Middleware support
- Event-driven architecture

## Installation

```bash
# Using bun (recommended)
bun add @aionbuilders/helios

# Using npm
npm install @aionbuilders/helios
```

**Requirements**: Bun v1.0+

## Quick Start

### Basic Server

```javascript
import { Helios } from '@aionbuilders/helios';

const helios = new Helios();

// Register a method
helios.method('user.get', async (context) => {
  return {
    id: context.payload.userId,
    name: "Alice"
  };
});

// Listen to events
helios.on('chat:message', async (data, context) => {
  console.log('Message:', data);
});

// Start server
helios.serve({ port: 3000 });
console.log('✨ Helios running on port 3000');
```

### With Session Recovery

```javascript
const helios = new Helios({
  sessionRecovery: {
    enabled: true,
    secret: process.env.SESSION_SECRET, // min 32 bytes
    ttl: 5 * 60 * 1000 // 5 minutes
  }
});

helios.events.on('session:recovered', ({ connection, session }) => {
  console.log('Session recovered:', session.sessionId);
});
```

### With Rooms (Broadcast)

```javascript
// Declare rooms with validators
helios.room('lobby', { type: 'public' });

helios.room('user:*', {
  validator: async (connection, captures) => {
    const [userId] = captures;
    return connection.data.get('userId') === userId;
  }
});

// Broadcast to room
helios.broadcast('lobby', {
  type: 'announcement',
  message: 'Welcome!'
});
```

### With Middleware

```javascript
// Global middleware
helios.use('**', async (context, next) => {
  console.log('Request:', context.method);
  const start = Date.now();

  const result = await next();

  console.log('Duration:', Date.now() - start, 'ms');
  return result;
});

// Namespace middleware
const api = helios.namespace('api');
api.use('**', async (context, next) => {
  // Auth check
  const token = context.connection.data.get('token');
  if (!token) {
    return context.createErrorResponse('Unauthorized', 401);
  }
  return await next();
});

api.register('users.list', async (context) => {
  return { users: [...] };
});
```

## Core Concepts

### Connection

Each WebSocket connection is wrapped in a `Connection` instance:

```javascript
helios.events.on('connection', ({ connection }) => {
  // Store user data
  connection.data.set('user', { id: 123, role: 'admin' });

  // Send messages
  connection.emit('welcome', { message: 'Hello!' });

  // Make requests
  const response = await connection.request('service.call', { ... });
});
```

### Methods (RPC)

Register methods that clients can call:

```javascript
helios.method('user.create', async (context) => {
  const { username, email } = context.payload;

  // Access connection
  const userId = context.connection.data.get('userId');

  // Return response
  return { id: newUserId, username };
});
```

### Events (Pub/Sub)

Subscribe to events from clients:

```javascript
helios.on('chat:message', async (data, context) => {
  // data = event payload
  // context = EventContext with connection info

  // Broadcast to others
  helios.broadcast('chat:room', {
    from: context.clientId,
    message: data.text
  });
});
```

### Rooms

Manage broadcast groups with permissions:

```javascript
// Public room
helios.room('lobby', { type: 'public' });

// Protected room with pattern
helios.room('document:*', {
  validator: async (connection, captures, data) => {
    const [docId] = captures;
    return await checkDocumentAccess(
      connection.data.get('userId'),
      docId
    );
  }
});

// Clients subscribe via RPC
// Built-in method: helios.subscribe
```

## Session Recovery

Connections can reconnect after network issues without losing state:

```javascript
const helios = new Helios({
  sessionRecovery: {
    enabled: true,
    secret: process.env.SESSION_SECRET,
    ttl: 5 * 60 * 1000 // 5 minutes
  }
});
```

**What's preserved:**
- ✅ `connection.data` Map
- ✅ Room subscriptions
- ✅ Pending requests
- ✅ All connection properties

See [SESSION_RECOVERY.md](./SESSION_RECOVERY.md) for details.

## Health Checks

Automatic ping/pong to detect dead connections:

```javascript
const helios = new Helios({
  healthCheck: {
    enabled: true,        // default: true
    interval: 30000,      // 30s
    timeout: 10000,       // 10s
    maxMissed: 2          // close after 2 missed pongs
  }
});

helios.events.on('ping-timeout', ({ connection }) => {
  console.log('Connection dead:', connection.id);
});
```

## API Reference

### Helios Options

```typescript
interface HeliosOptions {
  requestTimeout?: number;          // Default: 5000ms
  parseMode?: 'strict' | 'permissive'; // Default: 'strict'
  sessionRecovery?: SessionRecoveryOptions;
  healthCheck?: HealthCheckOptions;
}

interface SessionRecoveryOptions {
  enabled: boolean;
  secret: string;           // Required: 32+ bytes
  ttl?: number;             // Default: 300000ms (5 min)
}

interface HealthCheckOptions {
  enabled?: boolean;        // Default: true
  interval?: number;        // Default: 30000ms
  timeout?: number;         // Default: 10000ms
  maxMissed?: number;       // Default: 2
}
```

### Connection

```typescript
class Connection {
  id: string;
  sessionId: string | null;
  data: Map<string, any>;

  // Send messages
  send(message: Message): Promise<boolean>;
  emit(topic: string, data: any): Promise<boolean>;
  request(method: string, payload: any): Promise<Response>;

  // State
  state: 'OPEN' | 'CLOSING' | 'CLOSED';
}
```

### Events

```javascript
// Lifecycle
helios.events.on('connection', ({ connection, helios }) => { ... });
helios.events.on('disconnection', ({ connection, code, reason }) => { ... });

// Session Recovery
helios.events.on('session:recovered', ({ connection, session }) => { ... });
helios.events.on('session:refreshed', ({ connection, token }) => { ... });

// Rooms
helios.events.on('room:subscribed', ({ connection, topic }) => { ... });
helios.events.on('room:unsubscribed', ({ connection, topic }) => { ... });

// Health Checks
helios.events.on('ping-timeout', ({ connection }) => { ... });
helios.events.on('ping-missed', ({ connection, missedPongs }) => { ... });
helios.events.on('pong-received', ({ connection, latency }) => { ... });
```

## Examples

### Authentication

```javascript
helios.events.on('connection', async ({ connection }) => {
  // Wait for auth
  const timeout = setTimeout(() => {
    connection.ws.close(4001, 'Auth timeout');
  }, 5000);

  helios.events.once(`auth:${connection.id}`, ({ token }) => {
    clearTimeout(timeout);
    const user = validateToken(token);
    connection.data.set('user', user);
  });
});

helios.method('auth.login', async (context) => {
  const { username, password } = context.payload;
  const token = await authenticateUser(username, password);

  helios.events.emit(`auth:${context.connection.id}`, { token });

  return { success: true, token };
});
```

### Chat Room

```javascript
// Declare room
helios.room('chat:*', {
  validator: async (connection, captures) => {
    const [roomId] = captures;
    // Check if user has access to room
    return await hasRoomAccess(
      connection.data.get('userId'),
      roomId
    );
  }
});

// Handle messages
helios.on('chat:message', async (data, context) => {
  const user = context.connection.data.get('user');

  // Broadcast to room
  helios.broadcast(context.topic, {
    from: user.username,
    text: data.text,
    timestamp: Date.now()
  });
});
```

### Microservices Gateway

```javascript
const helios = new Helios();

// Service connections
const services = new Map();

helios.events.on('connection', ({ connection }) => {
  const serviceType = connection.data.get('serviceType');
  if (serviceType) {
    services.set(serviceType, connection);
  }
});

// Route to services
helios.method('gateway.**', async (context) => {
  const [, serviceName] = context.method.split('.');
  const service = services.get(serviceName);

  if (!service) {
    return context.createErrorResponse('Service unavailable', 503);
  }

  return await service.request(context.method, context.payload);
});
```

## Related Packages

- [@aionbuilders/helios-protocol](https://npm.im/@aionbuilders/helios-protocol) - Core protocol
- [@aionbuilders/starling](https://npm.im/@aionbuilders/starling) - Client implementation

## Development

```bash
# Install dependencies
bun install

# Run tests
bun test

# Run example server
bun run dev

# Watch mode
bun --watch tests/server.js
```

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

MIT © Killian Di Vincenzo

## Acknowledgments

Built with ❤️ using [Bun](https://bun.sh)
