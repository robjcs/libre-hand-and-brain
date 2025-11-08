import os
import json
import requests
import chess
from stockfish import Stockfish
from dotenv import load_dotenv
import threading
import logging

from chat_engine import ChatEngine

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LichessHandBrainBot:
    def __init__(self):
        self.token = os.getenv('LICHESS_TOKEN')
        self.bot_stockfish_level = int(os.getenv('STOCKFISH_LEVEL', 4))
        self.suggestion_stockfish_level = int(os.getenv('SUGGESTION_STOCKFISH_LEVEL', 15))
        self.bot_username = os.getenv('BOT_USERNAME', 'HandAndBrainBot')
        self.base_url = 'https://lichess.org'
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {self.token}'})
        self.bot_stockfish = None
        self.suggestion_stockfish = None
        self.active_games = {}
        self.bot_message_cache = {} # dont repeat messages in the same game

        self.chat = ChatEngine()
        
    def init_stockfish(self):
        try:
            # Bot's engine -- weak
            self.bot_stockfish = Stockfish()
            self.bot_stockfish.set_skill_level(self.bot_stockfish_level)
            
            # Stronger engine for suggestions to opponent
            self.suggestion_stockfish = Stockfish()
            self.suggestion_stockfish.set_skill_level(self.suggestion_stockfish_level)
            
            logger.info(f"Bot Stockfish initialized at level {self.bot_stockfish_level}")
            logger.info(f"Suggestion Stockfish initialized at level {self.suggestion_stockfish_level}")
        except Exception as e:
            logger.error(f"Failed to initialize Stockfish: {e}")
            return False
        return True
    
    def get_piece_name(self, move_uci, board):
        move = chess.Move.from_uci(move_uci)
        piece = board.piece_at(move.from_square)
        if not piece:
            return "Unknown"
        
        piece_names = {
            chess.PAWN: "Pawn",
            chess.ROOK: "Rook", 
            chess.KNIGHT: "Knight",
            chess.BISHOP: "Bishop",
            chess.QUEEN: "Queen",
            chess.KING: "King"
        }
        return piece_names.get(piece.piece_type, "Unknown")
    
    def get_best_move(self, fen, for_bot=True):
        engine = self.bot_stockfish if for_bot else self.suggestion_stockfish
        if not engine:
            return None
        
        try:
            # Set position using FEN directly
            engine.set_fen_position(fen)
            best_move = engine.get_best_move()
            return best_move
        except Exception as e:
            logger.error(f"Error getting best move: {e}")
            return None
    
    def send_chat_message(self, game_id, text):
        url = f"{self.base_url}/api/bot/game/{game_id}/chat"
        data = {'room': 'player', 'text': text}
        try:
            response = self.session.post(url, data=data)
            if response.status_code == 200:
                logger.info(f"[{game_id}] Chat message sent: {text}")
                if game_id not in self.bot_message_cache:
                    self.bot_message_cache[game_id] = []
                self.bot_message_cache[game_id].append(text)
                
            else:
                logger.error(f"Failed to send chat message: {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending chat message: {e}")
    
    def make_move(self, game_id, move_uci):
        url = f"{self.base_url}/api/bot/game/{game_id}/move/{move_uci}"
        try:
            response = self.session.post(url)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Failed to make move {move_uci}: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error making move: {e}")
            return False
    
    def handle_game_state(self, game_id, state, bot_color=None):
        try:
            moves = state.get('moves', '').split()
            board = chess.Board()
            
            for move in moves:
                if move:
                    board.push_uci(move)
            
            if bot_color is None or board.is_game_over():
                return
                
            fen = board.fen()
            
            logger.debug(f"[{game_id}] FEN: {fen}")
            
            if board.turn == bot_color:
                bot_move = self.get_best_move(fen, for_bot=True)
                
                if bot_move:
                    piece_name = self.get_piece_name(bot_move, board)
                    
                    if self.make_move(game_id, bot_move):
                        logger.info(f"[{game_id}] Bot made move: {bot_move} ({piece_name})")
                        
            else:
                if fen != 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1':
                    suggested_move = self.get_best_move(fen, for_bot=False)
                    
                    if suggested_move:
                        piece_name = self.get_piece_name(suggested_move, board)
                        cached_messages = self.bot_message_cache.get(game_id, [])
                        message = self.chat.generate_move_hint_message(piece_name, cached_messages)
                        self.send_chat_message(game_id, message)
                        logger.info(f"[{game_id}] Suggested to opponent: {suggested_move} ({piece_name})")
                    
        except Exception as e:
            logger.error(f"Error handling game state: {e}")
    
    def stream_game_events(self, game_id):
        url = f"{self.base_url}/api/bot/game/stream/{game_id}"
        bot_color = None

        cached_messages = self.bot_message_cache.get(game_id, [])
        self.send_chat_message(game_id, f"Hello! I'm {self.bot_username}! I will give you hints for your best move, but I'll only tell you the name of the piece you should move.")
        self.send_chat_message(game_id, f"Let's have a great game!")

        
        try:
            with self.session.get(url, stream=True) as response:
                for line in response.iter_lines():
                    if line:
                        try:
                            event = json.loads(line.decode('utf-8'))
                            event_type = event.get('type')
                            
                            if event_type == 'gameFull':
                                white_player = event.get('white', {})
                                black_player = event.get('black', {})
                                                                
                                if white_player.get('name') == self.bot_username:
                                    bot_color = chess.WHITE
                                    logger.info(f"[{game_id}] {self.bot_username} playing as White")
                                elif black_player.get('name') == self.bot_username:
                                    bot_color = chess.BLACK
                                    logger.info(f"[{game_id}] {self.bot_username} playing as Black")
                                
                                initial_state = event.get('state', {})
                                self.handle_game_state(game_id, initial_state, bot_color)
                                
                            elif event_type == 'gameState':
                                self.handle_game_state(game_id, event, bot_color)
                                
                            elif event_type == 'chatLine':
                                username = event.get('username', 'Unknown')
                                if username != self.bot_username:
                                    text = event.get('text', '')
                                    room = event.get('room', 'player')
                                
                                    logger.info(f"Chat from {username} in {room}: {text}")

                                    cached_messages = self.bot_message_cache.get(game_id, [])
                                    logger.info(f"Current cache for game {game_id}: {cached_messages}")
                                    message = self.chat.generate_chat_response(text, cached_messages)
                                    self.send_chat_message(game_id, message)
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Error streaming game {game_id}: {e}")
    
    def accept_challenge(self, challenge_id):
        url = f"{self.base_url}/api/challenge/{challenge_id}/accept"
        try:
            response = self.session.post(url)
            if response.status_code == 200:
                logger.info(f"Challenge {challenge_id} accepted")
                return True
            else:
                logger.error(f"Failed to accept challenge: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error accepting challenge: {e}")
            return False
    
    def stream_events(self):
        url = f"{self.base_url}/api/stream/event"
        try:
            with self.session.get(url, stream=True) as response:
                for line in response.iter_lines():
                    if line:
                        try:
                            event = json.loads(line.decode('utf-8'))
                            event_type = event.get('type')
                            
                            if event_type == 'challenge':
                                challenge = event.get('challenge', {})
                                challenge_id = challenge.get('id')
                                challenger = challenge.get('challenger', {}).get('name', 'Unknown')
                                
                                logger.info(f"Challenge received from {challenger}")
                                if self.accept_challenge(challenge_id):
                                    logger.info(f"Challenge from {challenger} accepted")
                                    
                            elif event_type == 'gameStart':
                                game = event.get('game', {})
                                game_id = game.get('id')
                                if game_id:
                                    logger.info(f"Game {game_id} started")
                                    thread = threading.Thread(
                                        target=self.stream_game_events, 
                                        args=(game_id,)
                                    )
                                    thread.daemon = True
                                    thread.start()
                                    self.active_games[game_id] = thread
                                    
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Error streaming events: {e}")
    
    def run(self):
        if not self.token:
            logger.error("LICHESS_TOKEN not found in environment variables")
            return
        
        if not self.init_stockfish():
            logger.error("Failed to initialize Stockfish")
            return
        
        logger.info("Hand and Brain Lichess bot starting...")
        logger.info(f"Bot plays at Stockfish level {self.bot_stockfish_level}")
        logger.info(f"Suggestions at Stockfish level {self.suggestion_stockfish_level}")
        logger.info("Waiting for challenges...")
        
        try:
            self.stream_events()

        except Exception as e:
            logger.error(f"Error: {e}")

if __name__ == "__main__":
    bot = LichessHandBrainBot()
    bot.run()