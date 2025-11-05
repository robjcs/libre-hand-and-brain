import os
import json
import time
import requests
import chess
import chess.engine
from stockfish import Stockfish
from dotenv import load_dotenv
import threading
import logging
import random

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LichessHandBrainBot:
    def __init__(self):
        self.token = os.getenv('LICHESS_TOKEN')
        self.bot_stockfish_level = int(os.getenv('STOCKFISH_LEVEL', 4))
        self.suggestion_stockfish_level = int(os.getenv('SUGGESTION_STOCKFISH_LEVEL', 15))
        self.base_url = 'https://lichess.org'
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {self.token}'})
        self.bot_stockfish = None
        self.suggestion_stockfish = None
        self.active_games = {}

        self.piece_suggestions = [
            "Hmm... I think you should move your {piece_name}",
            "How about the {piece_name}?",
            "Let's try moving a {piece_name}",
            "I'm feeling the {piece_name} here",
            "The {piece_name} looks promising",
            "Go with your {piece_name}",
            "Time for the {piece_name} to shine",
            "Your {piece_name} is calling",
            "I'd say {piece_name}",
            "Maybe the {piece_name}?",
            "The {piece_name} seems right",
            "Let's unleash the {piece_name}",
            "How about we move a {piece_name}?",
            "I'm thinking {piece_name}",
            "The {piece_name} could work well",
            "Try your {piece_name}",
            "What about the {piece_name}?",
            "I vote for the {piece_name}",
            "Let's go with the {piece_name}",
            "The {piece_name} is the move",
            "Move that {piece_name}!",
            "I'd pick the {piece_name}",
            "The {piece_name} looks good",
            "Use your {piece_name} here",
            "Let's see... the {piece_name}",
            "I'm leaning toward the {piece_name}",
            "The {piece_name}, definitely",
            "Trust me, move the {piece_name}",
            "The {piece_name} is perfect here",
            "I say we go {piece_name}",
            "The {piece_name} has potential",
            "Let's deploy the {piece_name}",
            "The {piece_name} is your best bet",
            "I'd recommend the {piece_name}",
            "How about a {piece_name} move?",
            "The {piece_name} looks juicy",
            "Let's activate the {piece_name}",
            "The {piece_name} feels right",
            "I'm seeing {piece_name} energy",
            "Go for the {piece_name}",
            "The {piece_name} is begging to move",
            "I'd move the {piece_name}",
            "Let's bring out the {piece_name}",
            "The {piece_name} is the play",
            "My instinct says {piece_name}",
            "The {piece_name} would be nice",
            "Let's make a {piece_name} move",
            "I'm getting {piece_name} vibes",
            "The {piece_name}, no doubt",
            "The {piece_name} is key here"
        ]
        
    def init_stockfish(self):
        try:
            # Bot's engine for making moves
            self.bot_stockfish = Stockfish()
            self.bot_stockfish.set_depth(self.bot_stockfish_level)
            
            # Stronger engine for suggestions to opponent
            self.suggestion_stockfish = Stockfish()
            self.suggestion_stockfish.set_depth(self.suggestion_stockfish_level)
            
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
            logger.info(f"{'Bot' if for_bot else 'Suggestion'} engine calculated move: {best_move} for position: {fen}")
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
                logger.info(f"Chat message sent: {text}")
            else:
                logger.error(f"Failed to send chat message: {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending chat message: {e}")
    
    def make_move(self, game_id, move_uci):
        url = f"{self.base_url}/api/bot/game/{game_id}/move/{move_uci}"
        try:
            response = self.session.post(url)
            if response.status_code == 200:
                logger.info(f"Move made: {move_uci}")
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
            move_count = len([m for m in moves if m])
            
            logger.info(f"Processing game state - Move #{move_count}")
            logger.info(f"Moves so far: {' '.join(moves) if moves else 'None'}")
            logger.info(f"Current turn: {'White' if board.turn == chess.WHITE else 'Black'}")
            logger.info(f"Bot color: {'White' if bot_color == chess.WHITE else 'Black'}")
            logger.info(f"Is bot's turn: {board.turn == bot_color}")
            logger.info(f"FEN: {fen}")
            
            if board.turn == bot_color:
                # Bot's turn: make move at bot level
                bot_move = self.get_best_move(fen, for_bot=True)
                
                if bot_move:
                    piece_name = self.get_piece_name(bot_move, board)
                    
                    if self.make_move(game_id, bot_move):
                        #message = f"I'm moving my {piece_name} ({bot_move})"
                        #self.send_chat_message(game_id, message)
                        logger.info(f"Bot made move: {bot_move} ({piece_name})")
                        
            else:
                # Opponent's turn: suggest best piece at max level (but don't make the move)
                suggested_move = self.get_best_move(fen, for_bot=False)
                
                if suggested_move:
                    piece_name = self.get_piece_name(suggested_move, board)
                    message = random.choice(self.piece_suggestions).format(piece_name=piece_name)
                    self.send_chat_message(game_id, message)
                    logger.info(f"Suggested to opponent: {suggested_move} ({piece_name})")
                    
        except Exception as e:
            logger.error(f"Error handling game state: {e}")
    
    def stream_game_events(self, game_id):
        url = f"{self.base_url}/api/bot/game/stream/{game_id}"
        bot_color = None
        
        try:
            with self.session.get(url, stream=True) as response:
                for line in response.iter_lines():
                    if line:
                        try:
                            event = json.loads(line.decode('utf-8'))
                            event_type = event.get('type')
                            
                            if event_type == 'gameFull':
                                # Determine bot's color from the game info
                                white_player = event.get('white', {})
                                black_player = event.get('black', {})
                                
                                # Get bot's username from API
                                profile_response = self.session.get(f"{self.base_url}/api/account")
                                if profile_response.status_code == 200:
                                    bot_username = profile_response.json().get('username', '')
                                    
                                    if white_player.get('name') == bot_username:
                                        bot_color = chess.WHITE
                                        logger.info(f"Bot playing as White in game {game_id}")
                                    elif black_player.get('name') == bot_username:
                                        bot_color = chess.BLACK
                                        logger.info(f"Bot playing as Black in game {game_id}")
                                
                                initial_state = event.get('state', {})
                                self.handle_game_state(game_id, initial_state, bot_color)
                                
                            elif event_type == 'gameState':
                                self.handle_game_state(game_id, event, bot_color)
                                
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
                                    self.send_chat_message(game_id, "Good luck! Let's have a great game! :)")
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
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    bot = LichessHandBrainBot()
    bot.run()