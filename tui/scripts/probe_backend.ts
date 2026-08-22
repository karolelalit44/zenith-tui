import { wsClient } from '../src/services/transport/WebSocketClient';
import { mapRawEvent } from '../src/services/transport/rawEventMapper';

const sessionId = process.argv[2];

const unsub = wsClient.onEvent((rpc) => {
  const { kind, data, id } = rpc.params;
  const mapped = mapRawEvent(kind, data, id);
  console.log(`\n--- ${kind} ---`);
  console.log(JSON.stringify(mapped, null, 2));
  if (kind === 'success' || kind === 'error') {
    unsub();
    wsClient.close();
    process.exit(0);
  }
});

wsClient.connect().then(async () => {
  const session = await wsClient.createSession('probe');
  const sid = session.id;
  console.log('SESSION', sid);
  await wsClient.sendPrompt('Say hi in one short sentence.', 'build', sid);
});
