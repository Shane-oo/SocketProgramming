Project made by Shane Monck (student id:22501734)

All tiers implemented
Test Environment:
    The Code was written and runs on a Mac.
    
    Matt Egan, made it aware that socket.MSG_DONTWAIT and socket.MSG_PEEK does not
    work on win32 (windows), if the project is run on win32 please uncomment the lines of code
    that are underneath the comment #win32 and then comment out the data line that has 
    (socket.MSG_DONTWAIT | socket.MSG_PEEK).
    Unforuntely I was not able to fully test the implementation of it running on both Mac and win32, so I have left the code that I know works the best on Mac, but incase the project is run only on win32 the code is there so that it could potentially work.

Note: The server.py does not pass the tester.py tests all the time, sometimes it does and sometimes it does not. Please if its possible test manually and see if my implementations were correct for the 
different tasks we had to do.

Lastly thank you to Jin Hong and the lab demonstrators, and a special thanks to Matt Egan for all his help on this project.