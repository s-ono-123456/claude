package com.example;

/**
 * C1 パス列挙のサンプルクラス
 */
public class Sample {

    /**
     * 絶対値を返す (if-else)
     */
    public int abs(int x) {
        if (x < 0) {
            return -x;
        } else {
            return x;
        }
    }

    /**
     * 1 から n までの合計 (while ループ)
     */
    public int sumTo(int n) {
        int result = 0;
        int i = 1;
        while (i <= n) {
            result = result + i;
            i = i + 1;
        }
        return result;
    }

    /**
     * 配列の最大値 (for ループ + if)
     */
    public int max(int[] arr) {
        if (arr == null || arr.length == 0) {
            return 0;
        }
        int max = arr[0];
        for (int i = 1; i < arr.length; i++) {
            if (arr[i] > max) {
                max = arr[i];
            }
        }
        return max;
    }

    /**
     * FizzBuzz 分類 (if-else if-else)
     */
    public String classify(int n) {
        if (n % 15 == 0) {
            return "FizzBuzz";
        } else if (n % 3 == 0) {
            return "Fizz";
        } else if (n % 5 == 0) {
            return "Buzz";
        } else {
            return String.valueOf(n);
        }
    }

    /**
     * 曜日名を返す (switch)
     */
    public String dayName(int day) {
        switch (day) {
            case 1:
                return "Monday";
            case 2:
                return "Tuesday";
            case 3:
                return "Wednesday";
            default:
                return "Other";
        }
    }

    /**
     * do-while を使った入力検証シミュレーション
     */
    public int countDigits(int n) {
        int count = 0;
        do {
            n = n / 10;
            count++;
        } while (n > 0);
        return count;
    }
}
