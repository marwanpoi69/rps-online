<template>
  <div class="max-w-6xl mx-auto">
    <!-- Header with Room Info -->
    <div class="bg-white bg-opacity-10 backdrop-blur-md rounded-xl p-4 mb-6">
      <div class="flex justify-between items-center">
        <div>
          <h2 class="text-2xl font-bold text-white">Room: {{ roomId }}</h2>
          <p class="text-lg text-white mb-1">Player: {{ playerName }}</p>
          <p class="text-blue-200">Players: {{ playersCount }}/2</p>
        </div>
        <div class="flex gap-4">
          <button 
            @click="restartGame"
            v-if="gameState === 'finished' || gameState === 'playing'"
            class="bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            🔄 Restart
          </button>
          <button 
            @click="leaveGame"
            class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            🚪 Leave
          </button>
        </div>
      </div>
    </div>

    <!-- Game Status -->
    <div class="text-center mb-6">
      <div 
        v-if="statusMessage" 
        class="bg-white bg-opacity-20 rounded-lg p-4 mb-4"
        :class="{'bg-red-500 bg-opacity-20': isError}"
      >
        <p class="text-2xl font-bold text-white">{{ statusMessage }}</p>
      </div>
      
      <!-- Countdown -->
      <div v-if="countdown > 0" class="text-6xl font-bold text-yellow-400 animate-pulse">
        {{ countdown }}
      </div>
    </div>

    <!-- Score Board -->
    <ScoreBoard :scores="scores" :player-names="playerNames" class="mb-6" />

    <!-- Turn Indicator -->
    <div v-if="gameState === 'playing'" class="text-center mb-6">
      <div class="bg-white bg-opacity-20 rounded-lg p-4">
        <p class="text-2xl font-bold text-white">
          <span v-if="isMyTurn">Your turn! Make your move</span>
          <span v-else>Waiting for opponent's move...</span>
        </p>
      </div>
    </div>

    <!-- Video Streams and Game Area -->
    <div class="grid md:grid-cols-2 gap-6 mb-6">
      <!-- Your Video -->
      <div>
        <VideoStream
          ref="localVideoStream"
          :is-local="true"
          :player-name="playerName || 'You'"
          :gesture="currentGesture"
          :confidence="gestureConfidence"
          @frame-captured="handleFrameCaptured"
        />
        <div v-if="currentGesture !== 'none'" class="mt-4 bg-white bg-opacity-20 rounded-lg p-4">
          <p class="text-white text-center">
            Detected: <span class="font-bold">{{ currentGesture.toUpperCase() }}</span>
            <span class="text-sm">({{ Math.round(gestureConfidence * 100) }}% confidence)</span>
          </p>
        </div>
      </div>

      <!-- Opponent Video -->
      <VideoStream
        :is-local="false"
        :player-name="opponentName"
        :stream-data="opponentVideoFrame"
      />
    </div>

    <!-- Game Controls -->
    <div class="text-center">
      <div v-if="gameState === 'waiting'" class="bg-white bg-opacity-20 rounded-lg p-6">
        <p class="text-xl text-white mb-4">Waiting for another player to join...</p>
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto"></div>
      </div>

      <div v-else-if="gameState === 'starting'" class="bg-white bg-opacity-20 rounded-lg p-6">
        <p class="text-xl text-white mb-4">Players Found! Get ready for the game</p>
        <button 
          @click="setReady"
          :disabled="isReady || playersCount < 2"
          class="bg-green-600 hover:bg-green-700 disabled:bg-gray-500 text-white px-8 py-3 rounded-lg font-bold transition-colors"
        >
          <span v-if="playersCount < 2">Waiting for players...</span>
          <span v-else>{{ isReady ? '✅ Ready!' : '🎯 Ready' }}</span>
        </button>
      </div>

      <div v-else-if="gameState === 'playing'" class="bg-white bg-opacity-20 rounded-lg p-6">
        <p class="text-xl text-white mb-4">{{ isMyTurn ? 'Show your move with hand gesture!' : 'Waiting for opponent...' }}</p>
        <div class="flex justify-center items-center space-x-8">
          <div class="text-center">
            <div class="text-4xl mb-2">✊</div>
            <p class="text-white">Rock</p>
          </div>
          <div class="text-center">
            <div class="text-4xl mb-2">✋</div>
            <p class="text-white">Paper</p>
          </div>
          <div class="text-center">
            <div class="text-4xl mb-2">✌️</div>
            <p class="text-white">Scissors</p>
          </div>
        </div>
      </div>

      <div v-else-if="gameState === 'finished'" class="bg-white bg-opacity-20 rounded-lg p-6">
        <p class="text-2xl font-bold text-white mb-4">🎉 Game Finished!</p>
        <p class="text-xl text-white mb-4">{{ gameWinner ? `${gameWinner} wins!` : 'It\'s a draw!' }}</p>
        <button 
          @click="restartGame"
          class="bg-green-600 hover:bg-green-700 text-white px-8 py-3 rounded-lg font-bold transition-colors"
        >
          🔄 Play Again
        </button>
      </div>
    </div>

    <!-- Round Result Modal -->
    <div v-if="showRoundResult" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-8 max-w-md mx-4 text-center">
        <h3 class="text-2xl font-bold mb-4">Round Result</h3>
        <div class="flex justify-center items-center space-x-8 mb-6">
          <div class="text-center">
            <p class="font-semibold mb-2">You</p>
            <div class="text-4xl">{{ getMoveEmoji(roundResult?.moves?.[playerId]) }}</div>
            <p class="text-sm text-gray-600">{{ roundResult?.moves?.[playerId] }}</p>
          </div>
          <div class="text-2xl">VS</div>
          <div class="text-center">
            <p class="font-semibold mb-2">Opponent</p>
            <div class="text-4xl">{{ getMoveEmoji(getOpponentMove()) }}</div>
            <p class="text-sm text-gray-600">{{ getOpponentMove() }}</p>
          </div>
        </div>
        <p class="text-xl font-bold mb-4">
          {{ getRoundResultText() }}
        </p>
        <button 
          @click="closeRoundResult"
          class="bg-blue-600 text-white py-2 px-6 rounded hover:bg-blue-700 transition-colors"
        >
          Continue
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import VideoStream from './VideoStream.vue'
import ScoreBoard from './ScoreBoard.vue'
import { WebSocketService } from '../services/websocket.js'

const props = defineProps({
  roomId: String,
  playerId: String,
  playerName: String
})

const emit = defineEmits(['leave-game'])

// Reactive state
const playersCount = ref(1)
const gameState = ref('waiting')
const statusMessage = ref('')
const isError = ref(false)
const countdown = ref(0)
const scores = ref({})
const currentGesture = ref('none')
const gestureConfidence = ref(0)
const isReady = ref(false)
const opponentVideoFrame = ref(null)
const opponentName = ref('Opponent')
const showRoundResult = ref(false)
const roundResult = ref(null)
const gameWinner = ref('')

// WebSocket instance
let wsService = null
const localVideoStream = ref(null)

// Computed
const playerNames = computed(() => {
  const names = {}
  names[props.playerId] = props.playerName || 'You'
  
  Object.keys(scores.value).forEach(id => {
    if (id !== props.playerId) {
      names[id] = 'Opponent'
    }
  })
  
  return names
})

const isMyTurn = computed(() => {
  if (!wsService?.currentTurn) return false
  return wsService.currentTurn === props.playerId
})

onMounted(async () => {
  try {
    wsService = new WebSocketService(props.roomId, props.playerId)
    
    wsService.on('player_joined', handlePlayerJoined)
    wsService.on('player_left', handlePlayerLeft)
    wsService.on('game_start', handleGameStart)
    wsService.on('countdown', handleCountdown)
    wsService.on('round_start', handleRoundStart)
    wsService.on('gesture_detected', handleGestureDetected)
    wsService.on('opponent_frame', handleOpponentFrame)
    wsService.on('round_result', handleRoundResult)
    wsService.on('next_round', handleNextRound)
    wsService.on('game_end', handleGameEnd)
    wsService.on('game_restarted', handleGameRestarted)
    wsService.on('turn_changed', handleTurnChanged)
    wsService.on('error', handleError)
    
    await wsService.connect()
  } catch (error) {
    console.error('Failed to initialize game:', error)
    showError('Failed to connect to game. Please try again.')
  }
})

onUnmounted(() => {
  if (wsService) {
    wsService.disconnect()
  }
})

// WebSocket event handlers
const handlePlayerJoined = (data) => {
  playersCount.value = data.players_count
  showStatus(`Player joined (${data.players_count}/2)`)
}

const handlePlayerLeft = (data) => {
  playersCount.value = data.players_count
  showError('Player left the game')
  gameState.value = 'waiting'
  isReady.value = false
}

const handleGameStart = (data) => {
  gameState.value = 'starting'
  showStatus(data.message)
}

const handleCountdown = (data) => {
  countdown.value = data.count
}

const handleRoundStart = (data) => {
  gameState.value = 'playing'
  showStatus(data.message)
  countdown.value = 0
  isReady.value = false
}

const handleGestureDetected = (data) => {
  currentGesture.value = data.gesture
  gestureConfidence.value = data.confidence
  
  if (isMyTurn.value && data.gesture !== 'none' && data.confidence > 0.7) {
    wsService.send({
      type: 'gesture_detected',
      gesture: data.gesture
    })
  }
}

const handleTurnChanged = (data) => {
  wsService.currentTurn = data.currentTurn
}

const handleOpponentFrame = (data) => {
  if (data.player_id !== props.playerId) {
    console.log('Received opponent frame from:', data.player_id)
    opponentVideoFrame.value = data.frame
  }
}

// Debug watch for opponent frame updates
watch(opponentVideoFrame, (newVal) => {
  console.log('Opponent video frame updated:', newVal ? 'has frame' : 'no frame')
})

const handleRoundResult = (data) => {
  roundResult.value = data
  scores.value = data.scores
  showRoundResult.value = true
  gameState.value = 'result'
}

const handleNextRound = (data) => {
  showStatus(data.message)
  closeRoundResult()
}

const handleGameEnd = (data) => {
  gameState.value = 'finished'
  gameWinner.value = playerNames.value[data.winner] || data.winner
  scores.value = data.final_scores
}

const handleGameRestarted = (data) => {
  gameState.value = 'starting'
  showStatus(data.message)
  scores.value = {}
  isReady.value = false
  gameWinner.value = ''
}

const handleError = (data) => {
  showError(data.message)
  if (data.message.includes('Waiting for another player')) {
    isReady.value = false
  }
}

// Game actions
const setReady = () => {
  if (isReady.value || playersCount.value < 2) return
  
  isReady.value = true
  wsService.send({
    type: 'player_ready'
  })
}

const restartGame = () => {
  wsService.send({
    type: 'restart_game'
  })
}

const leaveGame = () => {
  if (wsService) {
    wsService.disconnect()
  }
  emit('leave-game')
}

const handleFrameCaptured = (frameData) => {
  // Always send video frames when websocket is connected, regardless of game state
  // This ensures opponent can see your video during all game phases
  if (wsService && wsService.isConnected) {
    wsService.send({
      type: 'video_frame',
      frame: frameData,
      player_id: props.playerId
    })
  }
}

// Helper methods
const showStatus = (message) => {
  statusMessage.value = message
  isError.value = false
}

const showError = (message) => {
  statusMessage.value = message
  isError.value = true
}

const getMoveEmoji = (move) => {
  const emojis = {
    rock: '✊',
    paper: '✋',
    scissors: '✌️',
    none: '❌'
  }
  return emojis[move] || '❓'
}

const getOpponentMove = () => {
  if (!roundResult.value?.moves) return 'none'
  
  const moves = roundResult.value.moves
  const opponentId = Object.keys(moves).find(id => id !== props.playerId)
  return moves[opponentId] || 'none'
}

const getRoundResultText = () => {
  if (!roundResult.value) return ''
  
  const result = roundResult.value.result
  const winner = roundResult.value.winner
  
  if (result === 'draw') return "It's a draw!"
  if (winner === props.playerId) return "You win this round!"
  return "Opponent wins this round!"
}

const closeRoundResult = () => {
  showRoundResult.value = false
  roundResult.value = null
}
</script>
