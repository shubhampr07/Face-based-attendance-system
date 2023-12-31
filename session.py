import face_recognition
import cv2
import numpy as np
import json
import socket
import ast
import datetime

'''
During execution, this script obtains data from the server once, and constantly sends identified student ids to the 
server for attendance (Logics like if particular student attendance is already made, making attendence for student 
whose attendce is not made for a particular day is done by the server).

Student Face Encodings should be returned to this script in a dictionary format.
    * Key should be tuple of 122 dimentional face encoding converted from its orignal form of numpy array to use it as dict key
    * Value should be string of unique student identification in the following format:
        <student_id>-<university>
        For example: 23140736-BCU
'''


class Attendance:

    def __init__(self, server_ip_address: str, scale_frame=0.5, face_location_model='hog', face_encoding_model = 'small'):
        self.__server_ip_address = server_ip_address
        self.__face_encodings_transfer_port = 5001
        self.__face_encodings_transfer_chunksize = 100000
        self.__identified_ids_timestamps_transfer_port = 5002
        self.__identified_ids_timestamps_transfer_chunksize = 1024

        print('\nSession Started.....\n\nAttempting to recieve session data from the server..\n')

        def retrieve_faces_encodings() -> dict:
            '''Retrieves and retuns dictionary (key is face enoding and value is the student id) of faces encoding from the server'''
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.__server_ip_address, self.__face_encodings_transfer_port))

            # Receive the number of chunks
            num_chunks_data = sock.recv(self.__face_encodings_transfer_chunksize)
            num_chunks = int(num_chunks_data.decode())

            # Receive JSON data
            json_data = b""
            for _ in range(num_chunks):
                chunk = sock.recv(self.__face_encodings_transfer_chunksize)
                if not chunk:
                    break
                json_data += chunk

            # Decode and load the received JSON data
            encodings_data = json.loads(json_data.decode())

            sock.close()
            print("Session data received.\n")
            face_encodings_json = {ast.literal_eval(key): val for key, val in encodings_data.items()}
            return face_encodings_json

        self.__encodings_database = retrieve_faces_encodings()

        self.__encodings_database_encodings_only = [np.array(tuple_representation) for tuple_representation in self.__encodings_database.keys() ] # Getting faces encodings only from the database

        self.__identified_student_ids = []
        self.__identified_student_ids_with_timestamp = {} # This data will be sent to the server for attendance
        self.scale_frame = scale_frame

        self.face_location_model = face_location_model #'cnn' has better accuracy but uses GPU, 'hog' is faster with less accuracy uses cpu
        self.face_encoding_model = face_encoding_model #'large' model has better accuracy but is slower, 'small' model is faster

    def get_current_time(self):
        '''Gets the current timestamp, converts to string and returns it'''
        return str(datetime.datetime.now().time())
    
    def start_session(self, show_preview=True, camera_index=0, desired_fps=15):

        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((self.__server_ip_address, self.__identified_ids_timestamps_transfer_port))

        cap = cv2.VideoCapture(camera_index)
        frame_delay = int(1000 / desired_fps)  # Delay in milliseconds between frames based on the desired FPS
        
        while True:
            ret, frame = cap.read()

            small_frame = cv2.resize(frame, (0, 0), fx=self.scale_frame, fy=self.scale_frame) # Resize the frame for faster processing
            rgb_frame = small_frame[:, :, ::-1] # Convert the frame from BGR to RGB

            face_locations = face_recognition.face_locations(rgb_frame, model=self.face_location_model) # Find face locations and face encodings in the frame
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations) # Generate encodings of every faces in the frame in a list
            
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(self.__encodings_database_encodings_only, face_encoding) # Compare the face encoding with the list of known encoded faces
                if True in matches:
                    match_index = matches.index(True)
                    matched_encoding = self.__encodings_database_encodings_only[match_index]
                    identity = self.__encodings_database[tuple(matched_encoding)]
                else:
                    identity = 'Unknown'

                self.__identified_student_ids.append(identity)

                if identity != 'Unknown': # Add the studentid with timestamp only for known students in the database
                    self.__identified_student_ids_with_timestamp[identity] = self.get_current_time()

            if len(self.__identified_student_ids_with_timestamp) != 0: # Send data only if one or more person is detected
                
                identified_data_json = json.dumps(self.__identified_student_ids_with_timestamp).encode()
                
                total_bytes = len(identified_data_json)
                num_chunks = (total_bytes + self.__identified_ids_timestamps_transfer_chunksize - 1) // self.__identified_ids_timestamps_transfer_chunksize

                client_socket.sendall(str(num_chunks).encode() + b'\n')

                for i in range(0, total_bytes, self.__identified_ids_timestamps_transfer_chunksize):
                    chunk = identified_data_json[i:i + self.__identified_ids_timestamps_transfer_chunksize]
                    client_socket.sendall(chunk)

                print(f'[SENT]', self.__identified_student_ids_with_timestamp)
            

            if show_preview == True: 

                # Draw rectangles around detected faces and display names
                for (top, right, bottom, left), identity in zip(face_locations, self.__identified_student_ids):
                    top *= int(1 / self.scale_frame)
                    right *= int(1 / self.scale_frame)
                    bottom *= int(1 / self.scale_frame)
                    left *= int(1 / self.scale_frame)

                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.putText(frame, identity, (left, bottom + 20), cv2.FONT_HERSHEY_DUPLEX, 0.5, (0, 255, 0), 1)
                
                cv2.imshow('Students Identification', frame) # Display the frame with face rectangles
                
                if cv2.waitKey(frame_delay) & 0xFF == ord('q'): # Break the loop if 'q' key is pressed
                    break

            self.__identified_student_ids = [] #Reset the variable
            self.__identified_student_ids_with_timestamp = {} #Reset the variable

        client_socket.close() # Close the socket
        cap.release() # Release the camera
        cv2.destroyAllWindows() # Close the window

if __name__ == '__main__':
    session = Attendance(server_ip_address='192.168.1.64')
    session.start_session(show_preview=True)