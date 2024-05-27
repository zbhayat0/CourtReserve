from string import ascii_uppercase

def change(nth: int, powers: list[int]):
    if not nth:
        return 1

    powers = [p for p in powers if p<=nth and p>0]
    print(powers)
    powers.sort(reverse=True)
    f_power = powers.pop(0)
    dp = [1] + [not j%f_power for j in range(1, nth+1)]

    for power in powers:
        for j in range(power, nth+1):
            if jj:=dp[j-power]:
                dp[j] += jj

    return 0+dp[nth]


def count_plates(N, NUM_CHARACTERS=5):
    # Constants for ASCII values of uppercase letters
    ASCII_START = 65
    ASCII_END = 90
    
    # Initialize DP table
    dp = [[0 for _ in range(N+1)] for _ in range(NUM_CHARACTERS+1)]
    
    # Base case: 1 way to make sum 0 with 0 characters
    dp[0][0] = 1
    
    # Fill the DP table
    for i in range(1, NUM_CHARACTERS + 1):
        for j in range(N + 1):
            for c in range(ASCII_START, ASCII_END + 1):
                if j >= c:
                    dp[i][j] += dp[i-1][j-c]
    
    # The answer is the number of ways to form sum N with exactly 10 characters
    return dp[NUM_CHARACTERS][N]

# Example usage
N = 357  # Example value for N
print(count_plates(N, 5))

# ans = change(850, [ord(i) for i in ascii_uppercase])

# print(ans)