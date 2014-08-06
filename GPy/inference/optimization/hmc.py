"""HMC implementation"""

import numpy as np


class HMC:
    def __init__(self,model,M=None,stepsize=1e-1):
        self.model = model
        self.stepsize = stepsize
        self.p = np.empty_like(model.optimizer_array.copy())
        if M is None:
            self.M = np.eye(self.p.size)
        else:
            self.M = M
        self.Minv = np.linalg.inv(self.M)

    def sample(self, m_iters=1000, hmc_iters=20):
        thetas = np.empty((m_iters,self.p.size))
        ps = np.empty((m_iters,self.p.size))
        for i in xrange(m_iters):
            self.p[:] = np.random.multivariate_normal(np.zeros(self.p.size),self.M)
            H_old = self._computeH()
            p_old = self.p.copy()
            theta_old = self.model.optimizer_array.copy()
            #Matropolis
            self._update(hmc_iters)
            H_new = self._computeH()

            if H_old>H_new:
                k = 1.
            else:
                k = np.exp(H_old-H_new)
            if np.random.rand()<k:
                thetas[i] = self.model.optimizer_array
                ps[i] = self.p
            else:
                thetas[i] = theta_old
                ps[i] = p_old
                self.model.optimizer_array = theta_old
        return thetas, ps

    def _update(self, hmc_iters):
        for i in xrange(hmc_iters):
            self.p[:] += -self.stepsize/2.*self.model._transform_gradients(self.model.objective_function_gradients())
            self.model.optimizer_array = self.model.optimizer_array + self.stepsize*np.dot(self.Minv, self.p)
            self.p[:] += -self.stepsize/2.*self.model._transform_gradients(self.model.objective_function_gradients())

    def _computeH(self,):
        return self.model.objective_function()+self.p.size*np.log(2*np.pi)/2.+np.log(np.linalg.det(self.M))/2.+np.dot(self.p, np.dot(self.Minv,self.p[:,None]))/2.

class HMC_shortcut:
    def __init__(self,model,M=None,stepsize_range=[1e-6, 1e-1],groupsize=5, Hstd_th=[1e-3, 20.]):
        self.model = model
        self.stepsize_range = np.log10(stepsize_range)
        self.p = np.empty_like(model.optimizer_array.copy())
        self.groupsize = groupsize
        self.Hstd_th = Hstd_th
        if M is None:
            self.M = np.eye(self.p.size)
        else:
            self.M = M
        self.Minv = np.linalg.inv(self.M)

    def sample(self, m_iters=1000, hmc_iters=20):
        thetas = np.empty((m_iters,self.p.size))
        ps = np.empty((m_iters,self.p.size))
        for i in xrange(m_iters):
            # sample a stepsize from the uniform distribution
            stepsize = np.exp10(np.random.rand()*(self.stepsize_range[1]-self.stepsize_range[0])+self.stepsize_range[0])
            self.p[:] = np.random.multivariate_normal(np.zeros(self.p.size),self.M)
            H_old = self._computeH()
            p_old = self.p.copy()
            theta_old = self.model.optimizer_array.copy()
            #Matropolis
            self._update(hmc_iters, stepsize)
            H_new = self._computeH()

            if H_old>H_new:
                k = 1.
            else:
                k = np.exp(H_old-H_new)
            if np.random.rand()<k:
                thetas[i] = self.model.optimizer_array
                ps[i] = self.p
            else:
                thetas[i] = theta_old
                ps[i] = p_old
                self.model.optimizer_array = theta_old
        return thetas, ps

    def _update(self, hmc_iters, stepsize):
        theta_buf = np.empty((2*hmc_iters+1,self.model.optimizer_array.size))
        p_buf = np.empty((2*hmc_iters+1,self.p.size))
        H_buf = np.empty((2*hmc_iters+1,))
        # Set initial position
        theta_buf[hmc_iters] = self.model.optimizer_array
        p_buf[hmc_iters] = self.p
        H_buf[hmc_iters] = self._computeH()

        reversal = []
        pos = 1
        for i in xrange(hmc_iters):
            self.p[:] += -self.stepsize/2.*self.model._transform_gradients(self.model.objective_function_gradients())
            self.model.optimizer_array = self.model.optimizer_array + self.stepsize*np.dot(self.Minv, self.p)
            self.p[:] += -self.stepsize/2.*self.model._transform_gradients(self.model.objective_function_gradients())

            theta_buf[hmc_iters+pos] = self.model.optimizer_array
            p_buf[hmc_iters+pos] = self.p
            H_buf[hmc_iters+pos] = self._computeH()

            if i<self.groupsize:
                pos += 1
                continue
            else:
                if len(reversal)==0:
                    Hlist = range(pos,pos-self.groupsize,-1)
                    if self._testH(H_buf[Hlist]):
                        pos += 1
                    else:
                        # Reverse the trajectory for the 1st time
                        reversal.add(pos)
                        pos = -1
                        self.model.optimizer_array = theta_buf[hmc_iters]
                        self.p[:] = -p_buf[hmc_iters]
                else:
                    Hlist = range(pos,pos+self.groupsize)
                    if self._testH(H_buf[Hlist]):
                        pos += -1
                    else:
                        # Reverse the trajectory for the 2nd time
                        r = (hmc_iters - i)%((reversal[0]-pos)*2)
                        if r>(reversal[0]-pos):
                            pos_new = 2*reversal[0] - r - pos
                        else:
                            pos_new = 2*pos + r - reversal[0]
                        self.model.optimizer_array = theta_buf[hmc_iters+pos_new]
                        self.p[:] = p_buf[hmc_iters+pos_new] # the sign of momentum might be wrong!
                        break


    def _testH(self, Hlist):
        Hstd = np.std(Hlist)
        if Hstd<self.Hstd_th[0] or Hstd>self.Hstd_th[1]:
            return False
        else:
            return True

    def _computeH(self,):
        return self.model.objective_function()+self.p.size*np.log(2*np.pi)/2.+np.log(np.linalg.det(self.M))/2.+np.dot(self.p, np.dot(self.Minv,self.p[:,None]))/2.
