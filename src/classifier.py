import numpy as np
import pandas as pd
import re, math
from itertools import islice
from copy import deepcopy
from scipy import stats

#fast sliding window function
def window(iterable, size):
    it = iter(iterable)

    #this works because we knock out the first n elements
    #i.e.: you can only go through an iterator once
    result = tuple(islice(it, size))

    if len(result) == size:
        yield result
    for item in it:
        result = result[1:] + (item,)
        yield result


def chi_squarify(totaltokens, totalfeatures, smoother = 0):
    '''totaltokens should be a 3-tuple of the count of all positive,neutral, 
    and negative words, totalfeatures are total counts of the feature occurring in pos,neu,neg'''
    predictedfrequencies = []
    observedfrequencies = []
    n = totaltokens[0] + totaltokens[1] + totaltokens [2] + 6*smoother
    features = totalfeatures[0] + totalfeatures[1] + totalfeatures[2] + 3*smoother
    nonfeatures = n - features
    positive = totaltokens[0] + totalfeatures[0] +2 * smoother
    neutral = totaltokens[1] + totalfeatures[1] +2* smoother
    negative = totaltokens[2] + totalfeatures[2] + 2*smoother
    predictedfrequencies.append(float(positive*features/n))
    predictedfrequencies.append(float(neutral*features/n))
    predictedfrequencies.append(float(negative*features/n))
    predictedfrequencies.append(float(positive*nonfeatures/n))
    predictedfrequencies.append(float(neutral*nonfeatures/n))
    predictedfrequencies.append(float(negative*nonfeatures/n))
    observedfrequencies.append(totalfeatures[0] + smoother)
    observedfrequencies.append(totalfeatures[1] + smoother)
    observedfrequencies.append(totalfeatures[2] + smoother)
    observedfrequencies.append(totaltokens[0] - totalfeatures[0] + smoother)
    observedfrequencies.append(totaltokens[1] - totalfeatures[1] + smoother)
    observedfrequencies.append(totaltokens[2] - totalfeatures[2] + smoother)
    chistatistic = 0  
    for x in range (0,6):
        a = predictedfrequencies[x] - observedfrequencies[x]
        b = a*a/predictedfrequencies[x]
        chistatistic = b + chistatistic
    return chistatistic


#def chi_square_filter(fetures, smoother, cutoff):
#    returnedfeatures = []
#    for x in features:
#        y = chisquarify


class Classifier:
    '''
    n is the length of n-grams to use, should be set to 1 or 2
    k is the good-turing cutoff (i.e. we stop smoothing when count is > k)
    x is the smoothing parameter for the transition matrix
    c is the chi-square stat
    '''
    def __init__(self, std_format_text, n = 1, k = 5, x = 0, c = 5.): #n can equal 1,2,3

        self.n = n
        self.c = c

        self.sentiments = ["neg", "neu", "pos"]

        #no sense treating these as unknown
        self.seen_words = set(["!", ".", ",", "<s>", "</s>", ":", ";", "'", "\"", "/", "\\"]) 
        self.unk = "<unk>"

        self.A, self.sentences_by_sentiment = self.parse_text(std_format_text)

        #makes the transitions less biased towards staying in same state
        #we don't change the x --> </r> probabilities
        if x > 0:  
            for s1 in self.sentiments + ["<r>"]: #go down rows
                #go across cols
                total_prob = sum([self.A.loc[s1, x] for x in self.sentiments])

                for s2 in self.sentiments:
                    self.A.loc[s1, s2] = total_prob*(self.A.loc[s1, s2] + .1*x)/(total_prob + .3*x)

        if n >= 1:
            self.unigrams          = self.make_features(self.sentences_by_sentiment, 1)
            self.unigram_counts    = self.sum_counts(self.unigrams, 1)
            self.gt_unigrams       = self.good_turing(self.unigrams, 1, k)
            self.gt_unigram_counts = self.sum_counts(self.gt_unigrams, 1)
        if n >= 2:
            self.bigrams           = self.make_features(self.sentences_by_sentiment, 2)
            self.bigram_counts     = self.sum_counts(self.bigrams, 2)
            self.gt_bigrams        = self.good_turing(self.bigrams,  2, k)
            self.gt_bigram_counts  = self.sum_counts(self.gt_bigrams, 2)
        if n >= 3:
            self.trigrams          = self.make_features(self.sentences_by_sentiment, 3)
            self.trigram_counts    = self.sum_counts(self.trigrams, 3)
            self.gt_trigrams       = self.good_turing(self.trigrams, 3, k)
            self.gt_trigram_counts = self.sum_counts(self.gt_trigrams, 3)

        self.admissible_features = set()
        self.admissible()

    #converts text to dictionary keyed by sentiment
    #handles unknown words
    #with list of sentences as the values
    #also gets transition matrix
    def parse_text(self, std_format_text):

        sentence_sentiment_dict = {s: [] for s in self.sentiments}

        states = ["<r>", "neg", "neu", "pos", "</r>"]
        A = pd.DataFrame(np.zeros((5,5)), index = states, columns = states)
        A.loc["</r>", "</r>"] = 1 #just to prevent NAs

        #with open(path, 'rb') as f:
        #    text = f.read()

        #text = text.decode("utf-8")

        #text = re.split(r'\n\n', text)
        #text.pop()

        for review in std_format_text:

            r = self.clean_review(review)

            prev_sentiment = r.pop(0).split('\t')[0] #starting sentiment, <r>

            for line in r:

                sentiment, sentence = self.tokenize_sentence(line, self.n)

                #for unk
                for word in range(len(sentence)):
                    if sentence[word] not in self.seen_words:
                        self.seen_words.add(sentence[word]) #add to seen words
                        sentence[word] = self.unk #overwrite

                if sentiment not in ["<r>", "</r>"]:
                    sentence_sentiment_dict[sentiment].append(sentence)

                A.loc[prev_sentiment, sentiment] += 1
                prev_sentiment = sentiment

        try:
            self.seen_words.remove('')
        except:
            pass

        s = A.sum(axis=1)

        for item in s.index:
            A.loc[item,:] = A.loc[item,:]/s.loc[item] #divide row by row sum

        return A, sentence_sentiment_dict

    @staticmethod
    def clean_review(review):
        r = review.split("\n")
        review_type = r.pop(0)
        category, label, number = review_type.split("_")

        #add begin and end review tokens
        r = ["<r>\t"] + r + ["</r>\t"]

        return r

    #tokenizes sentence
    @staticmethod
    def tokenize_sentence(line, n):
        sentiment, sentence = line.split('\t')
        #make all lower: 
        sentence = sentence.lower()

        #puts whitespace around everything except words and whitespace
        sentence = re.sub(r'[^\w\s\']', ' \g<0> ', sentence)
        sentence = sentence.strip()

        #for ngrams n > 1, add n-1 start tokens and an end token
        if n > 1:
            sentence = sentence + " </s>"
            for x in range(n-1):
                sentence = "<s> " + sentence

        sentence = re.split(r' +', sentence)

        return sentiment, sentence

    def sum_counts(self, count_dict, n):
        sum_dict = {"pos": 0, "neg":0, "neu": 0}
        if n == 1:
            for s in self.sentiments:
                sum_dict[s] = sum([v for k, v in count_dict[s].items()])
        elif n == 2:
            for s in self.sentiments:
                for word1 in count_dict[s]:
                    sum_dict[s] += sum([v for k, v in count_dict[s][word1].items()])
        return sum_dict

    #gets unigrams if n = 1, bigrams if n = 2, etc.
    def make_features(self, parsed_text, z):
        feature_dict = {"pos": {}, "neg": {}, "neu": {}}

        for sentiment in parsed_text:
            for sentence in parsed_text[sentiment]:
                for n_gram in window(sentence, z):
                    if len(n_gram) == 1:
                        #need n_gram[0] because it's a tuple
                        #just pull out the underlying string
                        gram = n_gram[0]
                        if gram not in feature_dict[sentiment]:
                            feature_dict[sentiment][gram] = 0
                        feature_dict[sentiment][gram] += 1

                    #for bigrams and trigrams we do the "conditional feature" dict
                    elif len(n_gram) == 2:
                        w = n_gram[-1]
                        #beginning to second-to-last word
                        n_minus_one_gram = n_gram[:-1][0]

                        #dictionary here for fast lookup
                        if n_minus_one_gram not in feature_dict[sentiment]: 
                            feature_dict[sentiment][n_minus_one_gram] = {}
                        if w not in feature_dict[sentiment][n_minus_one_gram]:
                            feature_dict[sentiment][n_minus_one_gram][w] = 0
                        feature_dict[sentiment][n_minus_one_gram][w] += 1

        return feature_dict

    #smoothes counts
    #returns the updated count
    def good_turing(self, feature_dict, n, cutoff):
        '''
        we don't worry about 0 counts because of katz backoff
        '''
        smoothed_feature_dict = deepcopy(feature_dict)
        freq_of_freqs = {}

        #for unigrams
        if n == 1:
            for s in self.sentiments:
                for k, v in feature_dict[s].items():
                    if v not in freq_of_freqs:
                        freq_of_freqs[v] = 0
                    freq_of_freqs[v] += 1

            #smooth using the freq_of_freqs
            for s in self.sentiments:
                for f, v in feature_dict[s].items():
                    smoothed_feature_dict[s][f] = self.gt_counts(v, cutoff, freq_of_freqs)

                for word in self.seen_words:
                    if word not in smoothed_feature_dict[s]:
                        smoothed_feature_dict[s][word] = freq_of_freqs[1]/sum([v for k,v in freq_of_freqs.items()])

        #for bigrams/trigrams
        elif n > 1:
            for s in self.sentiments:
                for k1 in feature_dict[s]:
                    for k2, v in feature_dict[s][k1].items():
                        if v not in freq_of_freqs:
                            freq_of_freqs[v] = 0
                        freq_of_freqs[v] += 1

            #smooth feature dict
            for s in self.sentiments:
                for f1 in feature_dict[s]:
                    for f2, v in feature_dict[s][f1].items():
                        smoothed_feature_dict[s][f1][f2] = self.gt_counts(v, cutoff, freq_of_freqs)

        return smoothed_feature_dict

    @staticmethod
    def gt_counts(c, k, ffd): 
        '''
        c: MLE count
        k: cutoff
        ffd: freq of freq dict
        returns smoothed count
        '''
        if c > k:
            return c
        else:
            #c* equaiton from page 103
            return ( ( (c+1)*(ffd[c+1]/ffd[c]) ) - ( c*( (k + 1)*ffd[k+1] )/ffd[1] ) )/(1 - ( (k+1)*(ffd[k+1])/ffd[1] ) )

    #do this just for unigrams
    def admissible(self, kind = "chi"):
        if kind == "chi": 
            for word in self.seen_words:
                word_count = [self.gt_unigrams[x].get(word, 0) for x in self.sentiments]
                sentiment_count = [self.gt_unigram_counts[x] for x in self.sentiments]

                chi_sqr = chi_squarify(sentiment_count, word_count)

                if chi_sqr > self.c:
                    self.admissible_features.add(word)

        elif kind == "logodds":
            pass

    def return_prob(self, sentiment, words):
        if self.n == 1:
            log_prob_sum = 0
            for word in words:
                if word in self.admissible_features:
                    log_prob_sum += math.log(self.gt_unigrams[sentiment][word]/self.gt_unigram_counts[sentiment], 2)
                else:
                    continue
                    #log_prob_sum += math.log(self.gt_unigrams[sentiment]['<unk>']/self.gt_unigram_counts[sentiment], 2)
            return log_prob_sum

        if self.n == 2:
            log_prob_sum = 0
            for bigram in window(words, 2):
                log_prob_sum += self.katz_backoff_prob(bigram, sentiment)
            return log_prob_sum

    #give this a unigram, bigram, or trigram
    def katz_backoff_prob(self, n_gram, sentiment):
        if len(n_gram) == 2:
            #if we've seen the bigram
            w1, w2 = n_gram

            if w1 in self.bigrams[sentiment] and w2 in self.bigrams[sentiment][w1]:
                #sum of unsmoothed occurances of prev word
                if w1 in self.admissible_features or w2 in self.admissible_features:
                    s = sum([v for k, v in self.bigrams[sentiment][w1].items()])
                    return math.log(self.gt_bigrams[sentiment][w1][w2] / s, 2)
                else:
                    return 0
            elif w1 in self.bigrams[sentiment]:
                #intuitively: if w1 is not in bigrams, then default to unigram with full prob
                #if w1 is in bigrams but w2 is not in bigrams[w1], weighted unigram

                beta_complement = 0
                s = sum([v for k, v in self.bigrams[sentiment][w1].items()])

                for word in self.gt_bigrams[sentiment][w1]:
                    beta_complement += self.gt_bigrams[sentiment][w1][word]/s

                #denom is 1 since we're at the last step, so alpha = beta
                alpha = 1 - beta_complement

                if w1 in self.admissible_features or w2 in self.admissible_features:
                    return math.log(alpha*self.gt_unigrams[sentiment][w2], 2)
                else:
                    return 0

            elif w1 not in self.bigrams[sentiment]:
                if w2 in self.gt_unigrams[sentiment] and w2 in self.admissible_features:
                    return math.log(self.gt_unigrams[sentiment][w2], 2)
                else:
                    return 0
            else:
                return 0
        else:
            return math.log(self.gt_unigrams[sentiment][n_gram], 2)


    def viterbi(self, review):
        r = self.clean_review(review)
        r.pop()
        r.pop(0)

        ground_truth = [self.tokenize_sentence(x, self.n)[0] for x in r]

        sentences = [self.tokenize_sentence(x, self.n)[1] for x in r]

        for sentence in sentences:
            for word in range(len(sentence)):
                if sentence[word] not in self.seen_words:
                    sentence[word] = self.unk

        num_sentences = len(sentences)

        #this is the probabiliy of being in a state at time t
        viterbi_prob = pd.DataFrame(np.zeros([len(self.A.index), num_sentences]), index= self.A.index)

        #this is the most probable 
        backpointer = pd.DataFrame(np.zeros([len(self.A.index), num_sentences]), index = self.A.index)

        #initialize
        for sentiment in self.sentiments:
            b = sentences[0]
            viterbi_prob.loc[sentiment, 0] = math.log(self.A.loc["<r>", sentiment], 2) + self.return_prob(sentiment, b)
            backpointer.loc[sentiment, 0] = 0.

        #intermedate steps (recursion)
        for t in range(1, num_sentences):
            for s in self.sentiments: #s_prime prev state; s current state
                #does them both in one shot
                #uses the fact that max does the max of the first element of a tuple
                #so we tack the state name as the second element of a tuple, (log-prob, state)
                viterbi_prob.loc[s,t], backpointer.loc[s,t] = \
                    max( \
                    [ ( viterbi_prob.loc[s_prime, t-1] + \
                    math.log(self.A.loc[s_prime, s], 2) + \
                    self.return_prob(s, sentences[t]), s_prime) \
                    for s_prime in self.sentiments ] )

        #end step
        viterbi_prob.loc["</r>", num_sentences - 1], backpointer.loc["</r>", num_sentences - 1] = \
            max( [ ( viterbi_prob.loc[s, num_sentences - 1] + \
            math.log(self.A.loc[s, "</r>"], 2), s) for s in self.sentiments])

        sequence = [ backpointer.loc["</r>", num_sentences-1] ]
        row_lookup = backpointer.loc["</r>", num_sentences-1]

        for col in range(num_sentences - 1, -1, -1):
            row_lookup = backpointer.loc[row_lookup, col]
            sequence.append(row_lookup)

        sequence.reverse()
        sequence.pop(0)

        return sequence, ground_truth

    def correct_share(self, reviews):

        total = 0
        correct = 0

        for review in reviews:
            predicted, ground_truth = self.viterbi(review)
            for s in range(len(ground_truth)):
                total += 1
                if predicted[s] == ground_truth[s]:
                    correct += 1

        return correct/total
